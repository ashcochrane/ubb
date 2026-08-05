import logging
from decimal import Decimal

from django.db import transaction, IntegrityError
from django.db.models import F
from django.utils import timezone

from apps.billing.tenant_billing.models import PlatformFeeCarry, TenantBillingPeriod
from core.money import DEFAULT_CURRENCY, from_minor, to_minor

logger = logging.getLogger(__name__)


class TenantBillingService:
    @staticmethod
    def get_or_create_current_period(tenant):
        """Get or create the current month's open billing period for a tenant.

        Uses half-open interval [first_of_month, first_of_next_month).
        Uses timezone.now().date() for UTC-safe month boundaries.
        """
        today = timezone.now().date()
        first_of_month = today.replace(day=1)
        if today.month == 12:
            first_of_next_month = today.replace(year=today.year + 1, month=1, day=1)
        else:
            first_of_next_month = today.replace(month=today.month + 1, day=1)

        try:
            period, _ = TenantBillingPeriod.objects.get_or_create(
                tenant=tenant,
                period_start=first_of_month,
                period_end=first_of_next_month,
                defaults={"status": "open"},
            )
        except IntegrityError:
            # Race condition: partial unique index rejected a second open period.
            # Another request won the create — fetch the existing one.
            period = TenantBillingPeriod.objects.get(
                tenant=tenant,
                period_start=first_of_month,
                period_end=first_of_next_month,
            )
        return period

    @staticmethod
    def accumulate_usage(tenant, billed_cost_micros):
        """Atomically increment the current billing period's usage totals.

        Called synchronously in the usage recording hot path. The atomic
        UPDATE is fast (no select, just increment) so this does not add
        meaningful latency.
        """
        period = TenantBillingService.get_or_create_current_period(tenant)
        rows = TenantBillingPeriod.objects.filter(id=period.id, status="open").update(
            total_usage_cost_micros=F("total_usage_cost_micros") + billed_cost_micros,
            event_count=F("event_count") + 1,
        )
        if rows == 0:
            # Period was closed between get_or_create and update — get fresh period and retry once
            logger.warning(
                "accumulate_usage: period closed mid-request, retrying with fresh period",
                extra={"data": {"tenant_id": str(tenant.id), "period_id": str(period.id)}},
            )
            period = TenantBillingService.get_or_create_current_period(tenant)
            rows = TenantBillingPeriod.objects.filter(id=period.id, status="open").update(
                total_usage_cost_micros=F("total_usage_cost_micros") + billed_cost_micros,
                event_count=F("event_count") + 1,
            )
            if rows == 0:
                logger.error(
                    "accumulate_usage: retry also updated zero rows",
                    extra={"data": {"tenant_id": str(tenant.id), "period_id": str(period.id)}},
                )

    @staticmethod
    def _calculate_fees(tenant, period):
        """Calculate fees per product using ProductFeeConfig.

        Falls back to legacy percentage if no ProductFeeConfig rows exist.

        Returns the fee in **exact micros, not yet floored to the minor unit**
        (#199). R2 says everything between the per-line rounding and the money
        boundary is exact, and R3 says the minor unit is reached exactly once —
        so the floor belongs at the boundary, in ``_bank_fee_carry``, not here
        and not once per line. Flooring each line separately, as this used to,
        reached the minor unit once per fee config and lost a fraction at each:
        two half-cent lines came to nothing rather than to a cent.

        Sandbox tenants (F4.4) NEVER accrue platform fees: their periods close
        at 0 and generate_tenant_platform_invoices marks them invoiced with no
        Stripe call (the <=0 branch).

        Note for anyone who later persists the returned ``line_items``: they
        are this period's own accruals, so they do NOT sum to the period's
        ``platform_fee_micros``. They differ by the carry — what came in from
        last period, less what goes on to the next. That gap is the carry
        working, not a bug; a line-item breakdown that has to reconcile to the
        billed total needs a carry line of its own.
        """
        from apps.billing.tenant_billing.models import ProductFeeConfig

        if tenant.is_sandbox:
            return 0, []

        total_fee = 0
        line_items = []

        configs = list(ProductFeeConfig.objects.filter(tenant=tenant))

        if configs:
            for config in configs:
                if config.fee_type == "flat":
                    fee = config.config.get("amount_micros", 0)
                elif config.fee_type == "percentage":
                    pct = Decimal(str(config.config.get("percentage", "0")))
                    fee = int(Decimal(period.total_usage_cost_micros) * pct / Decimal(100))
                else:
                    continue

                total_fee += fee
                line_items.append({
                    "product": config.product,
                    "description": f"{config.product} fee ({config.fee_type})",
                    "amount_micros": fee,
                })
        else:
            # Legacy fallback: single percentage from billing config
            from apps.billing.queries import get_billing_config
            billing_config = get_billing_config(tenant.id)
            raw_fee = (
                Decimal(period.total_usage_cost_micros)
                * billing_config.platform_fee_percentage
                / Decimal(100)
            )
            fee = int(raw_fee)
            total_fee = fee
            line_items.append({
                "product": "platform",
                "description": "Platform fee",
                "amount_micros": fee,
            })

        return total_fee, line_items

    @staticmethod
    def _bank_fee_carry(period, exact_fee_micros):
        """R3's money boundary for the platform fee: floor once, carry the rest.

        Returns the billable amount — a whole number of minor units, so
        ``micros_to_cents`` at the Stripe boundary can go on being an assertion
        that this ran rather than a rounding policy of its own.

        Owns the sandbox rule as well as the arithmetic: a sandbox tenant
        accrues no fee (F4.4), so there is no remainder and NO row — not a row
        at zero, which would assert a fee relationship that does not exist
        (#142 §11). Keeping the skip here rather than at the call site means
        the rule holds for any caller, not just ``close_period``.

        Must be called inside ``close_period``'s transaction, under the
        ``select_for_update`` on the period. That lock is what makes the carry
        exactly-once: the status guard means a period is closed once, so its
        predecessor's remainder is consumed once, and the row written here
        commits with the fee it produced or not at all.

        The carry-in is a chain read of the tenant's most recent EARLIER
        period, where ``PostpaidResidualLedger`` deliberately uses an
        order-insensitive accumulator instead. The difference is that the
        hazard it was built for cannot arise here:
        ``uq_one_open_period_per_tenant`` admits one open period per tenant and
        only open periods are closed, so a tenant's closes are serialized and
        cannot double-consume a predecessor the way concurrent adjacent-period
        pushes could. That is a claim about the periods this codebase creates
        (``get_or_create_current_period``, always the current month) — a
        backdated period inserted by hand after a later one closed would read
        the wrong predecessor. The per-period row is what #142 §11 asked for,
        and the audit trail it buys is worth that bounded assumption.
        """
        if period.tenant.is_sandbox:
            return 0

        # The fee is UBB invoicing the tenant on UBB's OWN Stripe account,
        # always in the platform's currency (see the currency="usd" on the
        # invoice item in stripe_service.push_platform_fee_invoice) — not the
        # tenant's customer-facing default_currency.
        fee_currency = DEFAULT_CURRENCY

        carried_in = (
            PlatformFeeCarry.objects
            .filter(tenant=period.tenant,
                    billing_period__period_start__lt=period.period_start)
            .order_by("-billing_period__period_start")
            .values_list("carried_out_micros", flat=True)
            .first()
        ) or 0

        billable_minor, carried_out = to_minor(
            exact_fee_micros + carried_in, fee_currency)

        PlatformFeeCarry.objects.create(
            tenant=period.tenant, billing_period=period,
            carried_in_micros=carried_in, carried_out_micros=carried_out)

        if carried_in or carried_out:
            logger.info(
                "tenant_billing.platform_fee_carried",
                extra={"data": {
                    "period_id": str(period.id),
                    "tenant_id": str(period.tenant_id),
                    "exact_fee_micros": exact_fee_micros,
                    "carried_in_micros": carried_in,
                    "carried_out_micros": carried_out,
                }},
            )

        return from_minor(billable_minor, fee_currency)

    @staticmethod
    def close_period(period):
        """Reconcile then close a billing period, calculating platform fee.

        Reconciliation runs outside the transaction to get accurate totals
        before locking and closing.

        The fee reaches the currency's minor unit here and nowhere else (#199,
        R3): ``_calculate_fees`` returns exact micros, ``_bank_fee_carry``
        floors them once and banks the remainder against the tenant for the
        next period. Both return 0 for a sandbox tenant, which accrues no fee.
        """
        # Reconcile first — catches any accumulate_usage drift near month-end
        TenantBillingService.reconcile_period(period)

        with transaction.atomic():
            period = TenantBillingPeriod.objects.select_for_update().get(pk=period.pk)
            if period.status != "open":
                return

            fee_micros, line_items = TenantBillingService._calculate_fees(
                period.tenant, period
            )
            fee_micros = TenantBillingService._bank_fee_carry(period, fee_micros)

            period.status = "closed"
            period.platform_fee_micros = fee_micros
            period.save(update_fields=["status", "platform_fee_micros", "updated_at"])

    @staticmethod
    def reconcile_period(period):
        """Recompute a billing period's totals from actual UsageEvent records.

        Used as a belt-and-suspenders reconciliation for any accumulate_usage
        failures. Safe to run on open or closed periods.

        Reads via metering query interface — no direct model import.

        Policy (F4.2): platform fees accrue in the ARRIVAL period
        (basis="arrival" = created_at), matching the wall-clock live
        accumulate_usage counter. A backdated event arriving this month is
        fee-billed THIS month — otherwise the live accumulator and this
        reconcile would permanently disagree about backdated events (the
        accumulate-vs-reconcile drift asymmetry).
        """
        from apps.metering.queries import get_period_totals

        totals = get_period_totals(period.tenant_id, period.period_start,
                                   period.period_end, basis="arrival")
        recomputed_cost = totals["total_cost_micros"]
        recomputed_count = totals["event_count"]

        # Skip if no events found — avoids zeroing out periods where events
        # were recorded via accumulate_usage but aren't queryable here.
        if recomputed_count == 0 and period.event_count > 0:
            return

        if (recomputed_cost != period.total_usage_cost_micros
                or recomputed_count != period.event_count):
            logger.warning(
                "Billing period reconciliation drift detected",
                extra={"data": {
                    "period_id": str(period.id),
                    "tenant": period.tenant.name,
                    "stored_cost": period.total_usage_cost_micros,
                    "recomputed_cost": recomputed_cost,
                    "stored_count": period.event_count,
                    "recomputed_count": recomputed_count,
                }},
            )
            TenantBillingPeriod.objects.filter(id=period.id).update(
                total_usage_cost_micros=recomputed_cost,
                event_count=recomputed_count,
            )
