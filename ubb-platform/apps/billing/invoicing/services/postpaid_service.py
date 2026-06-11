import logging
from collections import defaultdict
from datetime import timedelta

import stripe
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.billing.stripe.services.stripe_service import stripe_call
from core.exceptions import StripeFatalError

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
        from apps.platform.events.outbox import write_event
        from apps.platform.events.schemas import UsageInvoicePushFailedPermanent

        # I5: the row, the unique (customer, period_start) constraint and the
        # stripe_customer_id check ALL key on the billing owner (pooled seat ->
        # business), so a seat passed directly can never mint a second invoice.
        passed_customer = customer
        customer = customer.resolve_billing_owner()

        # Phase 1 — claim
        with transaction.atomic():
            rec, _ = CustomerUsageInvoice.objects.select_for_update().get_or_create(
                tenant=tenant, customer=customer, period_start=period_start,
                defaults={"period_end": period_end, "currency": tenant.default_currency or "usd"})
            if passed_customer.id != customer.id:
                # A row keyed on the seat itself can never be transitioned by this
                # owner-first service — supersede it so reconcile stops retrying it.
                CustomerUsageInvoice.objects.filter(
                    tenant=tenant, customer=passed_customer, period_start=period_start,
                    status__in=["pending", "failed", "skipped"],
                ).update(status="skipped", skip_reason="seat_superseded")
            if rec.status in ("pushed", "pushing"):
                return rec
            if rec.status == "failed_permanent":
                return rec  # idempotent, no re-alert
            if rec.status in ("pending", "failed") and (
                rec.push_attempts >= settings.POSTPAID_PUSH_MAX_ATTEMPTS
                or (rec.first_attempted_at
                    and timezone.now() - rec.first_attempted_at
                        > timedelta(hours=settings.POSTPAID_PUSH_MAX_AGE_HOURS))
            ):
                rec.status = "failed_permanent"
                rec.save(update_fields=["status", "updated_at"])
                write_event(UsageInvoicePushFailedPermanent(
                    tenant_id=str(tenant.id), customer_id=str(customer.id),
                    period_start=period_start.isoformat(),
                    push_attempts=rec.push_attempts,
                    last_error=rec.last_attempt_error[:500],
                    stripe_invoice_id=rec.stripe_invoice_id,
                ))
                logger.error("billing.usage_push_failed_permanent", extra={"data": {
                    "usage_invoice_id": str(rec.id), "customer_id": str(customer.id),
                    "period_start": period_start.isoformat(),
                    "push_attempts": rec.push_attempts,
                    "stripe_invoice_id": rec.stripe_invoice_id}})
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
            rec.push_attempts += 1
            rec.first_attempted_at = rec.first_attempted_at or timezone.now()
            rec.save(update_fields=["total_billed_micros", "status", "push_attempts",
                                    "first_attempted_at", "updated_at"])

        # Phase 2 — Stripe (no DB transaction held)
        # Carry the prior period's sub-cent residual forward into this push.
        prior = (CustomerUsageInvoice.objects.filter(
            tenant=tenant, customer=customer, status="pushed",
            period_start__lt=period_start).order_by("-period_start").first())
        carry_in = prior.residual_micros if prior else 0
        try:
            standalone_id, items, residual_out = PostpaidUsageService._push_to_stripe(
                tenant, customer, rec, lines, period_start, carry_in=carry_in)
        except Exception as exc:
            # Sticky transient failure: stays 'failed' (retried by reconcile) until
            # the attempts/wall-clock cap above flips it to failed_permanent.
            CustomerUsageInvoice.objects.filter(id=rec.id, status="pushing").update(
                status="failed", last_attempt_error=repr(exc)[:500])
            raise

        # Phase 3 — record
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
        from apps.billing.invoicing.models import CustomerUsageInvoice

        connected = tenant.stripe_connected_account_id
        currency = (tenant.default_currency or "usd").lower()

        # Usage rides the billing OWNER's bill (pooled seat -> business). The caller
        # already re-keys on the owner (I5), so this is a defensive no-op kept so a
        # seat reaching here directly still lands on the same wallet as access + seats.
        owner = customer.resolve_billing_owner()

        # Floor each line to whole cents, carrying the sub-cent residual forward (Wave 4.5).
        # We compute the billable lines FIRST so an all-sub-cent period creates no invoice.
        cent_lines, residual = [], carry_in
        for i, (label, amount) in enumerate(lines):
            cent_micros = amount + residual          # fold carry into the first/largest line
            cents = cent_micros // 10_000
            residual = cent_micros - cents * 10_000
            if cents <= 0:
                continue
            cent_lines.append((i, label, cents, amount))
        if residual >= 10_000:
            logger.error("postpaid.residual_overflow", extra={"data": {
                "usage_invoice_id": str(rec.id), "residual_micros": residual}})

        # Sub-cent total: nothing billable this period — carry the residual, create NO
        # empty invoice (and never strand an unfinalized draft).
        if not cent_lines:
            return None, [], residual

        # I2: resume-not-recreate. Retrieve the pointer if we have one; otherwise do
        # the I4 metadata lookup (covers a crash between Invoice.create and the
        # pointer persist); only CREATE when neither finds an invoice.
        created = False
        if rec.stripe_invoice_id:
            inv = stripe_call(
                stripe.Invoice.retrieve, id=rec.stripe_invoice_id, stripe_account=connected)
            if getattr(inv, "deleted", False) is True or getattr(inv, "status", "") == "void":
                # I1: never mint a sibling next to a known invoice. A deliberate
                # void-rebill goes through repush_usage_invoice --rebill-void.
                logger.error("postpaid.stripe_invoice_unusable", extra={"data": {
                    "usage_invoice_id": str(rec.id),
                    "stripe_invoice_id": rec.stripe_invoice_id,
                    "stripe_status": getattr(inv, "status", "deleted")}})
                raise StripeFatalError(
                    f"Stripe invoice {rec.stripe_invoice_id} for usage invoice {rec.id} "
                    "is void/deleted; use repush_usage_invoice --rebill-void to replace it")
        else:
            inv = PostpaidUsageService._find_existing_invoice(rec, owner, connected)
        if inv is None:
            # B1: create the draft FIRST, then PIN each usage line to it via invoice=<id>.
            # Stripe's default pending_invoice_items_behavior is 'exclude'; un-pinned pending
            # items would NOT sweep, finalizing an EMPTY invoice and never billing usage.
            # C1: usage is ALWAYS its own finalized standalone invoice (correct-cycle).
            inv = stripe_call(
                stripe.Invoice.create, retryable=True, idempotency_key=f"usage-invoice-{rec.id}",
                customer=owner.stripe_customer_id, auto_advance=False, stripe_account=connected,
                metadata={"usage_invoice_id": str(rec.id), "tenant_id": str(tenant.id),
                          "period_start": period_start.isoformat()})
            created = True

        # Phase 2a — persist the pointer the moment the invoice exists, so every
        # later retry is retrieve-first even across idempotency-key expiry.
        CustomerUsageInvoice.objects.filter(id=rec.id, status="pushing").update(
            stripe_invoice_id=inv.id, push_phase="invoice_created")

        # A just-created invoice is a draft; only a retrieved/found one needs its
        # Stripe status consulted (and its already-pinned items recovered).
        inv_status = "draft" if created else getattr(inv, "status", "")

        if inv_status in ("open", "paid", "uncollectible"):
            # Adopt: a prior attempt finalized this invoice — zero Stripe writes.
            existing = PostpaidUsageService._list_invoice_items(inv.id, connected)
            items = [(label, orig_micros, existing[str(i)].id if str(i) in existing else "")
                     for i, label, cents, orig_micros in cent_lines]
            CustomerUsageInvoice.objects.filter(id=rec.id, status="pushing").update(
                push_phase="finalized")
            return inv.id, items, residual

        if inv_status != "draft":
            logger.error("postpaid.stripe_invoice_unusable", extra={"data": {
                "usage_invoice_id": str(rec.id), "stripe_invoice_id": inv.id,
                "stripe_status": inv_status}})
            raise StripeFatalError(
                f"Stripe invoice {inv.id} for usage invoice {rec.id} has unexpected "
                f"status {inv_status!r}")

        # Draft: pin only the MISSING lines (a resumed push may already have some).
        existing = {} if created else PostpaidUsageService._list_invoice_items(inv.id, connected)
        items = []
        for i, label, cents, orig_micros in cent_lines:
            prior_item = existing.get(str(i))
            if prior_item is not None:
                items.append((label, orig_micros, prior_item.id))
                continue
            desc = f"Usage {period_start:%Y-%m}" + (f" — {label}" if label else "")
            item = stripe_call(
                stripe.InvoiceItem.create, retryable=True,
                idempotency_key=f"usage-item-{rec.id}-{i}",
                customer=owner.stripe_customer_id, invoice=inv.id, amount=cents,
                currency=currency, description=desc, stripe_account=connected,
                metadata={"usage_invoice_id": str(rec.id), "line_index": str(i)})
            items.append((label, orig_micros, item.id))
        CustomerUsageInvoice.objects.filter(id=rec.id, status="pushing").update(
            push_phase="items_pinned")
        stripe_call(
            stripe.Invoice.finalize_invoice, retryable=True,
            idempotency_key=f"usage-finalize-{rec.id}", invoice=inv.id,
            auto_advance=True, stripe_account=connected)
        CustomerUsageInvoice.objects.filter(id=rec.id, status="pushing").update(
            push_phase="finalized")
        return inv.id, items, residual

    @staticmethod
    def _find_existing_invoice(rec, owner, connected):
        """I4 belt-and-braces: before any create, deterministically look for an
        invoice already minted for this row. Invoice.list + client-side metadata
        match (Invoice.search has freshness lag). Skips void invoices so a
        deliberately-voided invoice can be replaced (--rebill-void)."""
        created_gte = int((rec.created_at - timedelta(days=1)).timestamp())
        result = stripe_call(
            stripe.Invoice.list, customer=owner.stripe_customer_id,
            stripe_account=connected, created={"gte": created_gte}, limit=100)
        for inv in result.auto_paging_iter():
            if getattr(inv, "status", "") == "void":
                continue
            meta = getattr(inv, "metadata", None) or {}
            if meta.get("usage_invoice_id") == str(rec.id):
                return inv
        return None

    @staticmethod
    def _list_invoice_items(invoice_id, connected):
        """Items already pinned to the invoice, indexed by their line_index metadata.
        Legacy items without metadata are unindexable (blank item-id fallback)."""
        result = stripe_call(
            stripe.InvoiceItem.list, invoice=invoice_id, stripe_account=connected, limit=100)
        indexed = {}
        for item in result.auto_paging_iter():
            meta = getattr(item, "metadata", None) or {}
            line_index = meta.get("line_index")
            if line_index is not None:
                indexed[line_index] = item
        return indexed
