import logging
from collections import defaultdict

import stripe
from django.db import transaction
from django.utils import timezone

from apps.billing.stripe.services.stripe_service import stripe_call

logger = logging.getLogger("ubb.billing")


class PostpaidUsageService:
    @staticmethod
    def aggregate_lines(tenant, customer, period_start, period_end):
        """(total_micros, [(label, amount_micros), ...]); lines ALWAYS sum to total.
        A BUSINESS aggregates across its seats with one line per seat (external_id)."""
        from apps.metering.usage.models import UsageEvent
        if customer.account_type == "business":
            from apps.platform.customers.models import Customer
            seats = {s.id: s.external_id for s in Customer.all_objects.filter(parent=customer)}
            if not seats:
                return 0, []
            qs = UsageEvent.objects.filter(
                tenant=tenant, customer_id__in=list(seats.keys()),
                effective_at__date__gte=period_start, effective_at__date__lt=period_end)
            agg = defaultdict(int)
            for cid, billed in qs.values_list("customer_id", "billed_cost_micros"):
                agg[seats.get(cid, "(seat)")] += billed or 0
            lines = sorted(agg.items(), key=lambda kv: (-kv[1], kv[0]))
            total = sum(a for _, a in lines)
            return total, lines

        from apps.billing.invoicing.models import PostpaidUsageConfig
        cfg = PostpaidUsageConfig.objects.filter(tenant=tenant).first()
        group_by = cfg.usage_line_item_group_by if cfg else ""

        if not group_by:
            from apps.metering.queries import get_customer_cost_totals
            total = get_customer_cost_totals(tenant.id, customer.id, period_start, period_end)["billed_cost_micros"]
            return total, ([("", total)] if total > 0 else [])

        from apps.metering.usage.models import UsageEvent
        qs = UsageEvent.objects.filter(
            tenant=tenant, customer=customer,
            effective_at__date__gte=period_start, effective_at__date__lt=period_end)
        agg = defaultdict(int)
        if group_by.startswith("tag:"):
            tag_key = group_by[4:]
            for tags, billed in qs.values_list("tags", "billed_cost_micros"):
                label = (tags or {}).get(tag_key) or "(other)"
                agg[label] += billed or 0
        else:  # "product_id"
            for pid, billed in qs.values_list("product_id", "billed_cost_micros"):
                agg[pid or "(other)"] += billed or 0
        lines = sorted(agg.items(), key=lambda kv: (-kv[1], kv[0]))
        total = sum(a for _, a in lines)  # total IS the sum of lines, by construction
        return total, lines

    @staticmethod
    def push_customer_period(tenant, customer, period_start, period_end):
        from apps.billing.invoicing.models import CustomerUsageInvoice, UsageInvoiceLineItem

        # Phase 1 — claim
        with transaction.atomic():
            rec, _ = CustomerUsageInvoice.objects.select_for_update().get_or_create(
                tenant=tenant, customer=customer, period_start=period_start,
                defaults={"period_end": period_end, "currency": tenant.default_currency or "usd"})
            if rec.status == "pushed":
                return rec
            total, lines = PostpaidUsageService.aggregate_lines(tenant, customer, period_start, period_end)
            rec.total_billed_micros = total
            if total <= 0:
                rec.status, rec.skip_reason = "skipped", "no_usage"
                rec.save(update_fields=["total_billed_micros", "status", "skip_reason", "updated_at"])
                return rec
            if not customer.stripe_customer_id:
                rec.status, rec.skip_reason = "skipped", "no_stripe_customer"
                rec.save(update_fields=["total_billed_micros", "status", "skip_reason", "updated_at"])
                return rec
            if not tenant.stripe_connected_account_id or not tenant.charges_enabled:
                # Connected account not charge-ready -- never push an invoice to it.
                rec.status, rec.skip_reason = "skipped", "not_charge_ready"
                rec.save(update_fields=["total_billed_micros", "status", "skip_reason", "updated_at"])
                return rec
            rec.status = "pushing"
            rec.save(update_fields=["total_billed_micros", "status", "updated_at"])

        # Phase 2 — Stripe (no DB transaction held)
        # Carry the prior period's sub-cent residual forward into this push.
        prior = (CustomerUsageInvoice.objects.filter(
            tenant=tenant, customer=customer, status="pushed",
            period_start__lt=period_start).order_by("-period_start").first())
        carry_in = prior.residual_micros if prior else 0
        try:
            standalone_id, items, residual_out = PostpaidUsageService._push_to_stripe(
                tenant, customer, rec, lines, period_start, carry_in=carry_in)
        except Exception:
            CustomerUsageInvoice.objects.filter(id=rec.id, status="pushing").update(status="pending")
            raise

        # Phase 3 — record
        from apps.platform.events.outbox import write_event
        from apps.platform.events.schemas import UsageInvoicePushed
        with transaction.atomic():
            rec = CustomerUsageInvoice.objects.select_for_update().get(id=rec.id)
            if rec.status != "pushing":
                return rec
            for label, amount, item_id in items:
                UsageInvoiceLineItem.objects.create(
                    usage_invoice=rec, dimension=label, amount_micros=amount,
                    stripe_invoice_item_id=item_id)
            rec.status = "pushed"
            rec.stripe_invoice_id = standalone_id or ""
            rec.residual_micros = residual_out
            rec.pushed_at = timezone.now()
            rec.save(update_fields=["status", "stripe_invoice_id", "residual_micros", "pushed_at", "updated_at"])
            if residual_out or carry_in:
                logger.info("postpaid.residual_carried", extra={"data": {
                    "customer_id": str(customer.id), "period_start": period_start.isoformat(),
                    "carried_in": carry_in, "residual_micros": residual_out}})
            write_event(UsageInvoicePushed(
                tenant_id=str(tenant.id), customer_id=str(customer.id),
                period_start=period_start.isoformat(), total_billed_micros=rec.total_billed_micros,
                line_item_count=len(items), stripe_invoice_id=rec.stripe_invoice_id,
                residual_micros=residual_out))
        return rec

    @staticmethod
    def _push_to_stripe(tenant, customer, rec, lines, period_start, carry_in=0):
        connected = tenant.stripe_connected_account_id
        currency = (tenant.default_currency or "usd").lower()

        # Usage rides the billing OWNER's bill (pooled seat -> business). The close
        # task already targets the owner, but resolve defensively so a seat passed
        # directly still lands on the same wallet as access + seats.
        owner = customer.resolve_billing_owner()

        items = []
        residual = carry_in
        for i, (label, amount) in enumerate(lines):
            cent_micros = amount + residual          # fold carry into the first/largest line
            cents = cent_micros // 10_000
            residual = cent_micros - cents * 10_000
            if cents <= 0:
                continue
            desc = f"Usage {period_start:%Y-%m}" + (f" — {label}" if label else "")
            item = stripe_call(
                stripe.InvoiceItem.create, retryable=True,
                idempotency_key=f"usage-item-{rec.id}-{i}",
                customer=owner.stripe_customer_id, amount=cents, currency=currency,
                description=desc, stripe_account=connected)
            items.append((label, amount, item.id))

        # C1: usage is ALWAYS its own finalized standalone invoice (correct-cycle).
        inv = stripe_call(
            stripe.Invoice.create, retryable=True, idempotency_key=f"usage-invoice-{rec.id}",
            customer=owner.stripe_customer_id, auto_advance=False, stripe_account=connected)
        stripe_call(
            stripe.Invoice.finalize_invoice, retryable=True,
            idempotency_key=f"usage-finalize-{rec.id}", invoice=inv.id,
            auto_advance=True, stripe_account=connected)
        if residual >= 10_000:
            logger.error("postpaid.residual_overflow", extra={"data": {
                "usage_invoice_id": str(rec.id), "residual_micros": residual}})
        return inv.id, items, residual
