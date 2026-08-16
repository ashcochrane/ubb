import logging
from decimal import Decimal

from django.db import transaction, IntegrityError
from django.db.models import F
from django.utils import timezone

from apps.billing.tenant_billing.models import PlatformFeeCarry, TenantBillingPeriod
from apps.platform.event_types.quarantine import refuse_a_silent_close
from core.cost_totals import UNRESOLVED_EVENT_COUNT_KEY
from core.money import DEFAULT_CURRENCY, from_minor, to_minor
from core.time_windows import utc_day_start

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

        **A PERIOD HOLDING MONEY NOBODY HAS ACCOUNTED FOR DOES NOT CLOSE
        (#329).** ``refuse_a_silent_close`` is the kernel's own definition of
        "unresolved", built beside the table it reads precisely so that whoever
        wired the close would inherit it rather than write a second one. Billing
        calls it directly: ADR-001 lets any product import the platform kernel,
        and putting a read contract or a hook in between would be that second
        definition, one indirection away.

        It runs BEFORE the reconcile, so a period that will not close does not
        first do the work of closing: reconciliation reads every posting in the
        window and rewrites the period's totals, and none of that survives a
        refusal. The saving is one wasted pass per attempt rather than a
        recurring one — the sweeper above this runs monthly — but the ordering
        also decides what the refusal MEANS. Refusing after the rewrite would
        leave a period whose stored totals had moved and whose status had not,
        which is a period reporting one thing and holding another.

        It runs AFTER the status check, and that is the other half of the same
        rule. An already-closed period is not refused: it closed, and nothing
        about a name held later makes that untrue. Raising there would report a
        month as unaccounted-for on every subsequent call, for a close that
        already happened.

        **The refusal is not a partial close, and the two are different things.**
        A held name is an outstanding TENANT decision — map it, register it or
        dismiss it — so the close refuses until one is taken. An unresolved
        supplier cost is missing information that may never arrive, so the
        period closes on time and states how many costs it excluded. One late
        supplier invoice must not freeze a tenant's billing.
        """
        # A period that is not open has nothing to refuse and nothing to close.
        # This read is unlocked and can be stale, which is safe in the only
        # direction that matters: a stale "closed" skips a close rather than
        # performing one, and the authority is still the locked check below.
        if period.status != "open":
            return

        refuse_a_silent_close(
            tenant=period.tenant,
            # Keyword-only at the guard, and worth restating here: the two
            # instants are the same type, and an inverted window matches
            # nothing, reports nothing held, and lets the period close. The
            # bounds are the period's own, so the window is half-open at both
            # ends and one held charge cannot refuse two adjacent periods.
            opened_at=utc_day_start(period.period_start),
            closes_at=utc_day_start(period.period_end))

        # Reconcile first — catches any accumulate_usage drift near month-end
        totals = TenantBillingService.reconcile_period(period)

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

        # WHAT THE MONTH COULD NOT ACCOUNT FOR, SAID RATHER THAN INFERRED.
        # Both keys, always, including the zero: a count written only when it is
        # non-zero cannot be told apart from a count nobody wrote, and the pair
        # exists to remove exactly that ambiguity. The supplier total is a floor
        # wherever the count is above zero.
        #
        # OUTSIDE the transaction, and after it, so this states a close that
        # committed rather than one that was attempted. A period that was
        # already closed returns before reaching here and correctly says
        # nothing: it is not this call that closed it.
        #
        # AND A CLOSE WITH NO TRUSTED READ BEHIND IT IS A DIFFERENT STATEMENT,
        # not the same one with zeroes in it. Reconciliation returns `None` when
        # metering could see none of the postings the period's own counter says
        # it holds — so the month closed without UBB learning what was in it,
        # which is worth an operator's attention and is not a completeness
        # figure at all.
        if totals is None:
            logger.warning(
                "tenant_billing.period_closed_without_a_trusted_total",
                extra={"data": {
                    "period_id": str(period.id),
                    "tenant_id": str(period.tenant_id),
                }},
            )
            return

        logger.info(
            "tenant_billing.period_closed",
            extra={"data": {
                "period_id": str(period.id),
                "tenant_id": str(period.tenant_id),
                "total_provider_cost_micros":
                    totals["total_provider_cost_micros"],
                UNRESOLVED_EVENT_COUNT_KEY: totals[UNRESOLVED_EVENT_COUNT_KEY],
            }},
        )

    @staticmethod
    def reconcile_period(period):
        """Recompute a billing period's totals from actual Posting records.

        Used as a belt-and-suspenders reconciliation for any accumulate_usage
        failures. Safe to run on open or closed periods.

        Reads via metering query interface — no direct model import.

        Policy (F4.2): platform fees accrue in the ARRIVAL period
        (basis="arrival" = created_at), matching the wall-clock live
        accumulate_usage counter. A backdated event arriving this month is
        fee-billed THIS month — otherwise the live accumulator and this
        reconcile would permanently disagree about backdated events (the
        accumulate-vs-reconcile drift asymmetry).

        **Returns the totals it read, or `None` where it did not trust them**,
        so that ``close_period`` states what the month excluded without paying
        for the same window twice — and states nothing rather than zero where
        there was nothing to state. The supplier
        pair is read on the ARRIVAL basis for the same reason the fee accrues on
        it: a report about what a period left out has to be about the rows that
        period accounts for. That is a different question from the one the
        quarantine guard asks, which places a held name by when the call
        happened — a January charge repaired in March is January's in both
        directions.
        """
        from apps.metering.queries import get_period_totals

        totals = get_period_totals(period.tenant_id, period.period_start,
                                   period.period_end, basis="arrival")
        recomputed_cost = totals["total_cost_micros"]
        recomputed_count = totals["event_count"]

        # Skip if no events found — avoids zeroing out periods where events
        # were recorded via accumulate_usage but aren't queryable here.
        #
        # ⚠ AND RETURNS NOTHING, WHICH IS THE WHOLE POINT OF THE BRANCH. This
        # read disagreed with the live accumulator and was not trusted enough to
        # write down; handing it back as a supplier-cost pair would let the
        # close publish `unresolved_event_count: 0` — "this month excluded
        # nothing" — for exactly the window it just declined to believe. That is
        # the silent zero this slice exists to delete, one layer up. `None`
        # means UBB did not learn what this period holds, and the caller says so
        # rather than reporting a figure nobody computed.
        if recomputed_count == 0 and period.event_count > 0:
            return None

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

        return totals
