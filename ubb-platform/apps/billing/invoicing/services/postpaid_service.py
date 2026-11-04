import contextlib
import logging
from collections import defaultdict
from datetime import timedelta

import stripe
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.billing.stripe.services.stripe_service import (
    api_key_for_tenant, metadata_value, stripe_call)
from core.cost_totals import UNPRICED_EVENT_COUNT_KEY
from core.exceptions import StripeFatalError
from core.currency_policy import the_rails_currency
from core.money import minor_units, to_minor
from apps.platform.tenants.models import rail_environment_of, the_rail_is_open_in
from core.vocabulary import (
    SKIP_REASON_BELOW_MINOR_UNIT,
    SKIP_REASON_NOTHING_TO_BILL,
    SKIP_REASON_NOT_CHARGE_READY,
    SKIP_REASON_NO_STRIPE_CUSTOMER,
    SKIP_REASON_NO_USAGE,
    SKIP_REASON_PAYMENT_RAIL_CLOSED,
    SKIP_REASON_SEAT_SUPERSEDED,
    USAGE_INVOICE_STATUS_FAILED,
    USAGE_INVOICE_STATUS_FAILED_PERMANENT,
    USAGE_INVOICE_STATUS_PENDING,
    USAGE_INVOICE_STATUS_PUSHED,
    USAGE_INVOICE_STATUS_PUSHING,
    USAGE_INVOICE_STATUS_SKIPPED,
)

logger = logging.getLogger("ubb.billing")


def _warn_if_incomplete(tenant, customer, period_start, unpriced_events):
    """Say out loud when an invoice is being built on an incomplete total
    (#351).

    `Posting.billed_cost_micros` is nullable, and the read contract now reports
    how many postings each total could not include. This service turns those
    totals into invoice LINES, so a total missing prices here is money
    misstated — and silently: a seat whose every posting is unpriced bills
    exactly like a seat that emitted nothing.

    **This warns rather than refuses, deliberately.** #329 answered the
    equivalent question for supplier cost by refusing to close a period, and
    that was its own ticket with its own reviewed decision. Whether a period
    holding unresolved customer prices may be invoiced at all is the same kind
    of question and it is not this one's; what this ticket owes is that the fact
    exists and is visible rather than absorbed by a coalesce. The line to change
    when that decision is made is this one.
    """
    if not unpriced_events:
        return
    logger.warning("postpaid.usage_total_incomplete", extra={"data": {
        "tenant_id": str(tenant.id), "customer_id": str(customer.id),
        "period_start": period_start.isoformat(),
        UNPRICED_EVENT_COUNT_KEY: unpriced_events}})

@contextlib.contextmanager
def _a_raise_counts_an_attempt(rec_id):
    """Wrap stage 2 of a push (R10 Stage C3, F-8): whatever it raises is
    recorded on the already-committed row as one failed attempt
    (``PostpaidUsageService._record_failed_claim``), then re-raised unchanged
    for the caller to log. Entered OUTSIDE stage 2's atomic, so the record is
    written after the rollback, never inside it."""
    try:
        yield
    except Exception as exc:
        PostpaidUsageService._record_failed_claim(rec_id, exc)
        raise


# F5.5: a renewal draft older than this is too close to Stripe's ~1h
# auto-finalize to safely pin items into — fall back to standalone.
CONSOLIDATION_MAX_DRAFT_AGE_SECONDS = 45 * 60


class PostpaidUsageService:
    @staticmethod
    def aggregate_lines(tenant, customer, period_start, period_end):
        """(total_micros, [(label, amount_micros), ...]); lines ALWAYS sum to total.
        A BUSINESS aggregates the postings pinned to it as their billing owner,
        one line per customer that recorded them (external_id) — its pooled
        seats, and itself if it recorded any. All metering reads go through the
        apps.metering.queries contract; the seat-label mapping, "(other)"/"(seat)"
        merge and presentation sort stay here.

        ⚠ **THE BUSINESS SUMS ONLY WHAT IS PINNED TO IT** (R10 Stage C3, F-7).
        It summed every seat by `parent=` until C3, so an ALLOCATED business —
        whose seats are each their own billing owner — was invoiced for usage
        its seats owed. The pin is `Posting.billing_owner_id`, written by the
        recording path from `Customer.resolve_billing_owner()`; there is no
        second topology rule here to disagree with it.

        ⚠ **THE GROUPING IS AN AXIS OF THE ONE VOCABULARY** (#503, slice 7 §11),
        not a key — `PostpaidUsageConfig.invoice_line_grouping` holds a word the
        tenant's own discovery contract publishes, and the route that writes it
        refuses anything else.

        ⚠ **A STORED WORD THAT HAS SINCE STOPPED BEING AN AXIS RAISES, AND THE
        PERIOD CLOSE FAILS LOUDLY RATHER THAN RE-GROUPING QUIETLY.** That is a
        decision, not an oversight. Falling back to no grouping would bill the
        right TOTAL under the wrong shape without anyone being told — which is
        the silent fall-through this ticket deleted, wearing a better hat. It is
        also close to unreachable: the registry RETIRES a declared field rather
        than deleting it and retired fields stay groupable (ADR-0005 D8), the
        rollups are a closed set UBB owns, and the write surface refuses
        anything else. If it does happen, the failure lands on the path built
        for exactly this — bounded retries, then `failed_permanent` with its
        outbox alert — so an operator is told rather than a customer surprised.
        (True since R10 Stage C3, F-8: the claim is committed before this runs,
        and a raise here counts one attempt on it. Until then the raise rolled
        the claim back with it and the month left the retry lane unannounced.)

        **WHICH POSTINGS BECOME LINES IS THE READ CONTRACT'S RULE AND NOT
        THIS METHOD'S.** A waived charge and a metered call under a fixed-price
        unit of work carry no customer liability, so they produce no line —
        argued at `apps.metering.queries.
        INVOICE_LINE_STATES_WITH_NO_LIABILITY`, applied to both the per-seat and
        the grouped read, and stated in one place so the two halves of an
        invoice cannot disagree about what a customer owes."""
        if customer.account_type == "business":
            from apps.platform.customers.models import Customer
            from apps.metering.queries import get_billed_totals_by_customer
            totals = get_billed_totals_by_customer(
                tenant.id, customer.id, period_start, period_end)
            if not totals:
                return 0, []
            # A soft-deleted seat keeps its line: its usage is still owed.
            seats = dict(Customer.all_objects.filter(
                id__in=list(totals)).values_list("id", "external_id"))
            agg = defaultdict(int)
            for cid, row in totals.items():
                # THE READ CONTRACT ANSWERS A PAIR PER SEAT NOW (#351): the
                # resolved billed total, already coalesced by the shared helper,
                # and how many of that seat's postings it could not include.
                # The `or 0` that used to sit here is gone rather than moved —
                # the value cannot be `None`, and a coalesce in front of one
                # that cannot be reads as though it still guarded something.
                agg[seats.get(cid, "(seat)")] += row["billed_cost_micros"]
            _warn_if_incomplete(tenant, customer, period_start, sum(
                row[UNPRICED_EVENT_COUNT_KEY] for row in totals.values()))
            lines = sorted(agg.items(), key=lambda kv: (-kv[1], kv[0]))
            total = sum(a for _, a in lines)
            return total, lines

        from apps.billing.invoicing.models import PostpaidUsageConfig
        cfg = PostpaidUsageConfig.objects.filter(tenant=tenant).first()
        group_by = cfg.invoice_line_grouping if cfg else ""

        if not group_by:
            from apps.metering.queries import get_customer_cost_totals
            totals = get_customer_cost_totals(
                tenant.id, customer.id, period_start, period_end)
            total = totals["billed_cost_micros"]
            _warn_if_incomplete(tenant, customer, period_start,
                                totals[UNPRICED_EVENT_COUNT_KEY])
            # A ZERO TOTAL MAKES NO LINE: there is nothing to invoice. Not a
            # sign rule (#603 ruling 9) — a resolved total is a sum of known
            # prices, and a known price is never negative.
            return total, ([("", total)] if total != 0 else [])

        from apps.metering.queries import get_customer_billed_breakdown
        agg = defaultdict(int)
        unpriced = 0
        for label, billed, line_unpriced in get_customer_billed_breakdown(
                tenant.id, customer.id, period_start, period_end, group_by):
            agg[label] += billed
            unpriced += line_unpriced
        _warn_if_incomplete(tenant, customer, period_start, unpriced)
        lines = sorted(agg.items(), key=lambda kv: (-kv[1], kv[0]))
        total = sum(a for _, a in lines)  # total IS the sum of lines, by construction
        return total, lines

    @staticmethod
    def _park_failed_permanent(tenant, customer, rec, from_statuses, last_error=None):
        """Terminal flip: guarded status update + outbox alert + loud log.

        Must be called inside transaction.atomic() so the alert event commits
        with the flip (outbox contract). Guarded on from_statuses so a lost
        race writes neither the flip nor a duplicate alert. Returns True if
        this caller won the flip.

        F1.1: a terminal row keeps its pinned carry_in_micros PARKED — never
        auto-returned to the residual ledger, because the cent it funded may
        already sit on a finalized Stripe invoice. An operator repush resumes
        the row WITH its pin."""
        from apps.billing.invoicing.models import CustomerUsageInvoice
        from apps.platform.events.outbox import write_event
        from apps.platform.events.schemas import UsageInvoicePushFailedPermanent

        fields = {"status": USAGE_INVOICE_STATUS_FAILED_PERMANENT, "updated_at": timezone.now()}
        if last_error is not None:
            fields["last_attempt_error"] = last_error
        updated = CustomerUsageInvoice.objects.filter(
            id=rec.id, status__in=list(from_statuses)).update(**fields)
        if not updated:
            return False
        rec.status = USAGE_INVOICE_STATUS_FAILED_PERMANENT
        if last_error is not None:
            rec.last_attempt_error = last_error
        write_event(UsageInvoicePushFailedPermanent(
            tenant_id=str(tenant.id), customer_id=str(customer.id),
            period_start=rec.period_start.isoformat(),
            push_attempts=rec.push_attempts,
            last_error=rec.last_attempt_error[:500],
            stripe_invoice_id=rec.stripe_invoice_id,
        ))
        logger.error("billing.usage_push_failed_permanent", extra={"data": {
            "usage_invoice_id": str(rec.id), "customer_id": str(customer.id),
            "period_start": rec.period_start.isoformat(),
            "push_attempts": rec.push_attempts,
            "stripe_invoice_id": rec.stripe_invoice_id}})
        return True

    @staticmethod
    def _record_failed_claim(rec_id, exc):
        """Stage 2 raised (R10 Stage C3, F-8): count ONE attempt and keep the
        error on the row, which stays in the retry lane as ``failed`` —
        ``reconcile_postpaid_usage`` retries it, and the attempts/age caps at
        the top of stage 2 park it ``failed_permanent`` with its alert.

        Stage 2 rolled back, so the row holds exactly what stage 1 committed
        (or what an earlier attempt left): nothing here touches the snapshot,
        the carry or any pointer. Guarded on the two statuses a counted attempt
        starts from, so a row another worker has moved on since is never
        clobbered; a skipped row whose re-evaluation raised stays skipped (the
        hourly recovery re-queues a recoverable one as ``pending``). Never
        masks the caller's exception: a failure to record is logged."""
        from django.db.models import F, Value
        from django.db.models.functions import Coalesce
        from apps.billing.invoicing.models import CustomerUsageInvoice

        now = timezone.now()
        try:
            CustomerUsageInvoice.objects.filter(
                id=rec_id,
                status__in=[USAGE_INVOICE_STATUS_PENDING, USAGE_INVOICE_STATUS_FAILED],
            ).update(
                status=USAGE_INVOICE_STATUS_FAILED,
                push_attempts=F("push_attempts") + 1,
                first_attempted_at=Coalesce(F("first_attempted_at"), Value(now)),
                last_attempt_error=repr(exc)[:500],
                updated_at=now)
        except Exception:
            logger.exception("postpaid.claim_failure_unrecorded", extra={"data": {
                "usage_invoice_id": str(rec_id)}})

    @staticmethod
    def push_customer_period(tenant, customer, period_start, period_end):
        """Push one billing owner's usage for one calendar month to Stripe.

        ⚠ **THE ROW IS THE RETRY UNIT, AND IT EXISTS BEFORE ANYTHING CAN
        THROW** (R10 Stage C3, F-8). Until C3 the claim was born inside the
        atomic that aggregates, so a raise there rolled it back and the month
        vanished from retry: nothing for ``reconcile_postpaid_usage`` to find,
        and the monthly close only ever addresses the month just ended.

        - **Stage 1 — the claim.** ``get_or_create`` the (owner, period) row as
          ``pending`` and COMMIT it: the durable retry identity and nothing
          else. No carry is reserved, nothing is aggregated or posted, Stripe
          is not called, no event is written, and the period is not consumed —
          a fresh ``pending`` row with no snapshot leaves it open to backfill
          (``apps.billing.queries.is_usage_period_closed``).
        - **Stage 2 — one atomic, exactly as before:** the holding supersede,
          the caps, the snapshot and its tripwire, the aggregation, the skips,
          the carry reservation and the flip to ``pushing``. A raise anywhere
          in it rolls all of that back and leaves the row ``failed`` with the
          error and one attempt counted (``_record_failed_claim``) — the
          tripwire's live re-aggregation on a resumed row included.
        - **Phase 2** — Stripe, no transaction held. **Phase 3** — record.
        """
        from apps.billing.invoicing.models import (
            CustomerUsageInvoice, PostpaidResidualLedger, UsageInvoiceLineItem)

        # I5: the row, the unique (customer, period_start) constraint and the
        # stripe_customer_id check ALL key on the billing owner (pooled seat ->
        # business), so a seat passed directly can never mint a second invoice.
        passed_customer = customer
        customer = customer.resolve_billing_owner()

        # Stage 1 — the claim, committed (F-8). Its own short transaction: the
        # unique (customer, period_start) constraint makes a concurrent claim
        # of the same period find this row rather than mint a second one.
        with transaction.atomic():
            rec, _ = CustomerUsageInvoice.objects.get_or_create(
                tenant=tenant, customer=customer, period_start=period_start,
                defaults={"period_end": period_end, "currency": tenant.default_currency})

        # Stage 2 — supersede, caps, snapshot/tripwire, aggregation, skips,
        # carry and the flip to pushing: one atomic under the row lock. A raise
        # anywhere in it rolls the atomic back FIRST (the inner manager exits
        # first), and only then counts the attempt on the committed row.
        with _a_raise_counts_an_attempt(rec.id), transaction.atomic():
            rec = CustomerUsageInvoice.objects.select_for_update().get(id=rec.id)
            if passed_customer.id != customer.id:
                # A row keyed on the seat itself can never be transitioned by this
                # owner-first service — supersede it so reconcile stops retrying it.
                CustomerUsageInvoice.objects.filter(
                    tenant=tenant, customer=passed_customer, period_start=period_start,
                    status__in=[USAGE_INVOICE_STATUS_PENDING, USAGE_INVOICE_STATUS_FAILED, USAGE_INVOICE_STATUS_SKIPPED],
                ).update(status=USAGE_INVOICE_STATUS_SKIPPED, skip_reason=SKIP_REASON_SEAT_SUPERSEDED)
            if rec.status in (USAGE_INVOICE_STATUS_PUSHED, USAGE_INVOICE_STATUS_PUSHING):
                return rec
            if rec.status == USAGE_INVOICE_STATUS_FAILED_PERMANENT:
                return rec  # idempotent, no re-alert
            if (rec.status == USAGE_INVOICE_STATUS_SKIPPED
                    and rec.skip_reason == SKIP_REASON_BELOW_MINOR_UNIT):
                # F-9 (RULED Q5): this period's carry has already moved —
                # consumed and deposited once — so it is terminal. Re-running
                # it would move the carry a second time.
                return rec
            if rec.status in (USAGE_INVOICE_STATUS_PENDING, USAGE_INVOICE_STATUS_FAILED) and (
                rec.push_attempts >= settings.UBB_POSTPAID_PUSH_MAX_ATTEMPTS
                or (rec.first_attempted_at
                    and timezone.now() - rec.first_attempted_at
                        > timedelta(hours=settings.UBB_POSTPAID_PUSH_MAX_AGE_HOURS))
            ):
                PostpaidUsageService._park_failed_permanent(
                    tenant, customer, rec, from_statuses=(USAGE_INVOICE_STATUS_PENDING, USAGE_INVOICE_STATUS_FAILED))
                return rec
            # Freeze-at-first-claim: line_index identity is positional over the
            # aggregation sort, so re-aggregating on a retry (after the tenant
            # flips the invoice-line grouping axis) would diff the WRONG indices
            # and overbill a resumed invoice. The first claim pins the lines;
            # every later attempt consumes the frozen snapshot by construction.
            if rec.line_snapshot:
                lines = [(label, amount) for label, amount in rec.line_snapshot]
                total = sum(amount for _, amount in lines)
                # F4.2 tripwire: the snapshot was frozen in a PRIOR claim
                # (this branch only runs when it existed before this claim),
                # so any event that slipped into the period since — the
                # ms-wide guard-read→commit race, or a closed-period-predicate
                # hole — is permanently excluded from these lines. Recompute
                # the live aggregate and page on mismatch. Alert-only, never
                # mutate: the frozen lines are what bills; the log is the
                # operator's signal.
                live_total, _ = PostpaidUsageService.aggregate_lines(
                    tenant, customer, period_start, period_end)
                if live_total != total:
                    logger.error("postpaid.snapshot_divergence", extra={"data": {
                        "usage_invoice_id": str(rec.id),
                        "customer_id": str(customer.id),
                        "period_start": period_start.isoformat(),
                        "frozen_total": total, "live_total": live_total}})
            else:
                total, lines = PostpaidUsageService.aggregate_lines(
                    tenant, customer, period_start, period_end)
                rec.line_snapshot = [[label, amount] for label, amount in lines]
            rec.total_billed_micros = total
            if total == 0:
                # NOTHING TO BILL IS NOT NO USAGE (#603 ruling 9). A period
                # whose usage was all priced at exactly nothing totals zero as
                # an empty one does, and labelling it `no_usage` said the
                # customer did nothing. Both skips are terminal; only the
                # words differ, and they are the truth about the period.
                from apps.metering.queries import (
                    billing_owner_recorded_anything)
                recorded = billing_owner_recorded_anything(
                    tenant.id, customer.id, period_start, period_end)
                rec.status, rec.skip_reason = USAGE_INVOICE_STATUS_SKIPPED, (
                    SKIP_REASON_NOTHING_TO_BILL if recorded else SKIP_REASON_NO_USAGE)
                rec.save(update_fields=["total_billed_micros", "status", "skip_reason", "updated_at"])
                return rec
            if not customer.stripe_customer_id:
                rec.status, rec.skip_reason = USAGE_INVOICE_STATUS_SKIPPED, SKIP_REASON_NO_STRIPE_CUSTOMER
                rec.save(update_fields=["total_billed_micros", "status", "skip_reason", "updated_at"])
                return rec
            if not tenant.stripe_connected_account_id or not tenant.charges_enabled:
                # Connected account not charge-ready -- never push an invoice to it.
                rec.status, rec.skip_reason = USAGE_INVOICE_STATUS_SKIPPED, SKIP_REASON_NOT_CHARGE_READY
                rec.save(update_fields=["total_billed_micros", "status", "skip_reason", "updated_at"])
                return rec
            if not the_rail_is_open_in(rail_environment_of(is_sandbox=tenant.is_sandbox)):
                # G27's flag, operationally: no new invoice on a closed rail.
                # RECOVERABLE — the reconcile re-queues it once the rail
                # reopens — never parked as a failure nobody repushes.
                rec.status, rec.skip_reason = USAGE_INVOICE_STATUS_SKIPPED, SKIP_REASON_PAYMENT_RAIL_CLOSED
                rec.save(update_fields=["total_billed_micros", "status", "skip_reason", "updated_at"])
                return rec
            # F1.1 carry reservation: take-and-zero the owner's residual ledger
            # and PIN the value on the row, exactly once per row. Sits AFTER
            # every skip check so a row that never pushes can never strand the
            # carry (zero usage + nonzero ledger stays banked for a future
            # month — sub-cent residue alone never mints an invoice). A retry
            # after a Phase-2 failure reuses the pin: never a second
            # reservation. Lock order: rec (claimed above) -> ledger,
            # everywhere this pair is touched.
            if rec.carry_in_micros is None:
                ledger, _ = PostpaidResidualLedger.objects.select_for_update().get_or_create(
                    customer=customer, defaults={"tenant": tenant})
                rec.carry_in_micros = ledger.balance_micros
                ledger.balance_micros = 0
                ledger.save(update_fields=["balance_micros", "updated_at"])
            rec.status = USAGE_INVOICE_STATUS_PUSHING
            rec.push_attempts += 1
            rec.first_attempted_at = rec.first_attempted_at or timezone.now()
            rec.save(update_fields=["total_billed_micros", "line_snapshot", "status",
                                    "carry_in_micros", "push_attempts",
                                    "first_attempted_at", "updated_at"])

        # Phase 2 — Stripe (no DB transaction held)
        # The carry-in was reserved from the residual ledger at claim time and
        # pinned on the row, so every attempt replays the same value (non-NULL
        # by construction once status reached pushing; `or 0` is defensive).
        carry_in = rec.carry_in_micros or 0
        try:
            invoice_id, items, residual_out = PostpaidUsageService._push_to_stripe(
                tenant, customer, rec, lines, period_start, carry_in=carry_in)
        except StripeFatalError as exc:
            # Non-retryable by definition (void/deleted/unexpected-status invoice,
            # auth/config, idempotency mismatch — see stripe_call): park terminal
            # NOW instead of burning ~8 hourly sticky-failed retries before the
            # alert. Retryable failures stay in the generic branch below.
            rec.refresh_from_db()  # pick up the pointer Phase 2a may have persisted
            with transaction.atomic():
                PostpaidUsageService._park_failed_permanent(
                    tenant, customer, rec, from_statuses=(USAGE_INVOICE_STATUS_PUSHING,),
                    last_error=repr(exc)[:500])
            return rec
        except Exception as exc:
            # Sticky transient failure: stays 'failed' (retried by reconcile) until
            # the attempts/wall-clock cap above flips it to failed_permanent.
            CustomerUsageInvoice.objects.filter(id=rec.id, status=USAGE_INVOICE_STATUS_PUSHING).update(
                status=USAGE_INVOICE_STATUS_FAILED, last_attempt_error=repr(exc)[:500])
            raise

        # Phase 3 — record
        from apps.platform.events.outbox import write_event
        from apps.platform.events.schemas import UsageInvoicePushed
        with transaction.atomic():
            rec = CustomerUsageInvoice.objects.select_for_update().get(id=rec.id)
            if rec.status != USAGE_INVOICE_STATUS_PUSHING:
                return rec
            # Belt-and-braces: a forced re-record (operator repush of a row that
            # already recorded once) must replace, never duplicate, line items.
            rec.line_items.all().delete()
            if invoice_id is None:
                # F-9 (RULED Q5): nothing reached one minor unit, so no Stripe
                # invoice exists and none was created. The period is SKIPPED
                # `below_minor_unit` — never `pushed`, which always means a
                # real Stripe invoice — and no `usage_invoice.pushed` is
                # written. Its carry still moves, exactly once, as the push
                # would have moved it: the pinned carry-in is consumed and the
                # residual deposited below. That is the deliberate exception to
                # "a skip reserves no carry", and the row is terminal (stage 2
                # returns early for it, and repush refuses it), so a replay can
                # never move the carry twice.
                rec.status = USAGE_INVOICE_STATUS_SKIPPED
                rec.skip_reason = SKIP_REASON_BELOW_MINOR_UNIT
                rec.residual_micros = residual_out
                rec.last_attempt_error = ""
                rec.save(update_fields=["status", "skip_reason", "residual_micros",
                                        "last_attempt_error", "updated_at"])
            else:
                for label, amount, item_id in items:
                    UsageInvoiceLineItem.objects.create(
                        usage_invoice=rec, grouping_field_value=label,
                        amount_micros=amount,
                        stripe_invoice_item_id=item_id)
                rec.status = USAGE_INVOICE_STATUS_PUSHED
                rec.stripe_invoice_id = invoice_id
                rec.residual_micros = residual_out
                rec.pushed_at = timezone.now()
                rec.last_attempt_error = ""
                rec.save(update_fields=["status", "stripe_invoice_id", "residual_micros",
                                        "pushed_at", "last_attempt_error", "updated_at"])
            # F1.1 deposit: bank this push's residual for whichever period
            # reserves next (rec lock held above -> ledger lock: the same
            # rec-then-ledger order as the Phase-1 reservation). The
            # status != "pushing" guard means a stale-reclaimed loser can
            # never reach here to double-deposit. The ledger exists by
            # construction: the Phase-1 reservation get_or_create'd it.
            if not (0 <= residual_out < minor_units(rec.currency)):
                logger.error("billing.residual_out_of_range", extra={"data": {
                    "usage_invoice_id": str(rec.id), "customer_id": str(customer.id),
                    "residual_out": residual_out}})
            ledger = PostpaidResidualLedger.objects.select_for_update().get(customer=customer)
            ledger.balance_micros += residual_out
            ledger.save(update_fields=["balance_micros", "updated_at"])
            if residual_out or carry_in:
                logger.info("postpaid.residual_carried", extra={"data": {
                    "customer_id": str(customer.id), "period_start": period_start.isoformat(),
                    "carried_in": carry_in, "residual_micros": residual_out}})
            if invoice_id is None:
                return rec
            write_event(UsageInvoicePushed(
                tenant_id=str(tenant.id), customer_id=str(customer.id),
                period_start=period_start.isoformat(), total_billed_micros=rec.total_billed_micros,
                line_item_count=len(items), stripe_invoice_id=rec.stripe_invoice_id,
                residual_micros=residual_out))
        return rec

    @staticmethod
    def _push_to_stripe(tenant, customer, rec, lines, period_start, carry_in=0):
        from apps.billing.invoicing.models import CustomerUsageInvoice, PostpaidUsageConfig

        connected = tenant.stripe_connected_account_id
        # The usage invoice row is the authoritative monetary object: its
        # currency is what every line is floored in and sent in, never the
        # tenant's setting at push time (#565). Refused before any Stripe call.
        currency = the_rails_currency(f"usage invoice {rec.id}", rec.currency)

        # Critical-1: --rebill-void rotates EVERY idempotency-key family. Within
        # Stripe's 24h key window the legacy keys would replay the recorded
        # responses — the now-void invoice, its items, its finalize — and Phase 3
        # would record 'pushed' against the corpse with the customer never
        # rebilled. Generation 0 keeps the exact legacy strings so in-flight
        # rows keep replaying their original keys.
        gen = f"-g{rec.rebill_generation}" if rec.rebill_generation else ""

        # Usage rides the billing OWNER's bill (pooled seat -> business). The caller
        # already re-keys on the owner (I5), so this is a defensive no-op kept so a
        # seat reaching here directly still lands on the same wallet as access + seats.
        owner = customer.resolve_billing_owner()

        # Floor each line to whole cents, carrying the sub-cent residual forward (Wave 4.5).
        # We compute the billable lines FIRST so an all-sub-cent period creates no invoice.
        cent_lines, residual = [], carry_in
        for i, (label, amount) in enumerate(lines):
            cent_micros = amount + residual          # fold carry into the first/largest line
            # R3's floor-with-carry: the remainder comes BACK from the helper,
            # so this loop cannot drop it by forgetting to compute it.
            cents, residual = to_minor(cent_micros, currency)
            # A line under one minor unit bills nothing this period; its
            # micros are carried. Never negative: a line sums known prices.
            if cents == 0:
                continue
            cent_lines.append((i, label, cents, amount))
        if residual >= minor_units(currency):
            logger.error("postpaid.residual_overflow", extra={"data": {
                "usage_invoice_id": str(rec.id), "residual_micros": residual}})

        # Sub-cent total: nothing billable this period — carry the residual, create NO
        # empty invoice (and never strand an unfinalized draft). Phase 3 records
        # the period `skipped` / `below_minor_unit` (F-9, RULED Q5). Nothing
        # Stripe-side is touched, so the key is not even read until after this.
        if not cent_lines:
            return None, [], residual
        api_key = api_key_for_tenant(tenant)

        # I2: resume-not-recreate. Retrieve the pointer if we have one; otherwise do
        # the I4 metadata lookup (covers a crash between Invoice.create and the
        # pointer persist); only CREATE when neither finds an invoice.
        created = False
        consolidated = False
        if rec.stripe_invoice_id:
            inv = stripe_call(
                stripe.Invoice.retrieve, api_key=api_key,
                id=rec.stripe_invoice_id, stripe_account=connected)
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
            # F5.5: a pointer on a "consolidated" rec is the subscription
            # renewal — a FOREIGN invoice (Stripe minted it; it carries none of
            # our invoice metadata) that finalizes on Stripe's clock. The
            # metadata check is defensive: an invoice WE minted (standalone or
            # split remainder) must always resume through the self-controlled
            # standalone path below, whatever the audit column says, because
            # our drafts are auto_advance=False and only finalize when we say.
            # A real Invoice's metadata is a StripeObject, not a dict (F-3a).
            consolidated = (rec.invoice_kind == "consolidated"
                            and metadata_value(inv, "usage_invoice_id") != str(rec.id))
        else:
            inv = PostpaidUsageService._find_existing_invoice(rec, owner, connected, api_key)
            if inv is None:
                # F5.5 opt-in consolidation: resolve a renewal-draft target only
                # when no invoice of OURS exists yet (a metadata match means a
                # prior attempt already went standalone — never fork it).
                cfg = PostpaidUsageConfig.objects.filter(tenant=tenant).first()
                if cfg is not None and cfg.consolidate_with_subscription:
                    inv = PostpaidUsageService._resolve_consolidation_target(
                        tenant, owner, rec, connected, api_key)
                    consolidated = inv is not None
        if inv is None:
            # F5.3: opt-in Stripe Tax passthrough — one of EXACTLY two
            # automatic_tax call sites (the other: Subscription.create). A
            # tax-config error from Stripe here is an InvalidRequestError ->
            # StripeFatalError -> parked failed_permanent with the outbox
            # alert after ONE attempt (the F0.1 machinery).
            extra = {}
            if tenant.automatic_tax_enabled:
                extra["automatic_tax"] = {"enabled": True}
            # B1: create the draft FIRST, then PIN each usage line to it via invoice=<id>.
            # Stripe's default pending_invoice_items_behavior is 'exclude'; un-pinned pending
            # items would NOT sweep, finalizing an EMPTY invoice and never billing usage.
            # C1: standalone usage is its own finalized invoice (correct-cycle);
            # F5.5 consolidation rides the renewal draft only via the explicit
            # opt-in target resolution above, never via subscription= pending items.
            inv = stripe_call(
                stripe.Invoice.create, api_key=api_key, retryable=True,
                idempotency_key=f"usage-invoice-{rec.id}{gen}",
                customer=owner.stripe_customer_id, auto_advance=False, stripe_account=connected,
                metadata={"usage_invoice_id": str(rec.id), "tenant_id": str(tenant.id),
                          "period_start": period_start.isoformat()},
                **extra)
            created = True

        # Phase 2a — persist the pointer (and which KIND of invoice it is) the
        # moment the target is known, BEFORE any item create, so every later
        # retry is retrieve-first even across idempotency-key expiry.
        # F5.5 Fix 1: capture the update count. If 0, this worker's claim was
        # stolen (another retry reclaimed a stale-pushing row and is already
        # in flight). Raise immediately — the exception handler's guarded
        # filter(status="pushing") will no-op for us (we no longer own the
        # row), so there is zero state damage.  The new owner will resume from
        # its own fresh Phase-2a; double-billing is impossible.
        from apps.billing.invoicing.models import CustomerUsageInvoice as _CUI
        _updated = _CUI.objects.filter(id=rec.id, status=USAGE_INVOICE_STATUS_PUSHING).update(
            stripe_invoice_id=inv.id, push_phase="invoice_created",
            invoice_kind="consolidated" if consolidated else "standalone")
        if _updated == 0:
            raise RuntimeError(
                f"postpaid.claim_lost: stale worker, aborting before item create "
                f"(usage_invoice_id={rec.id})")

        if consolidated:
            return PostpaidUsageService._push_consolidated(
                tenant, owner, rec, inv, cent_lines, residual, gen,
                connected, api_key, currency, period_start)

        # A just-created invoice is a draft; only a retrieved/found one needs its
        # Stripe status consulted (and its already-pinned items recovered).
        inv_status = "draft" if created else getattr(inv, "status", "")

        if inv_status in ("open", "paid", "uncollectible"):
            # Adopt: a prior attempt finalized this invoice — zero Stripe writes.
            existing = PostpaidUsageService._list_invoice_items(inv.id, connected, api_key)
            items = [(label, orig_micros, existing[str(i)].id if str(i) in existing else "")
                     for i, label, cents, orig_micros in cent_lines]
            absent = [str(i) for i, label, cents, orig_micros in cent_lines
                      if str(i) not in existing]
            if absent:
                # Alert-only tripwire: an adopted (already-finalized) invoice is
                # missing frozen lines — pre-metadata legacy items, or a voided
                # consolidated target whose lines died with it. The operator
                # owns the resolution; the record below is what billed.
                logger.error("postpaid.adopt_missing_lines", extra={"data": {
                    "usage_invoice_id": str(rec.id), "stripe_invoice_id": inv.id,
                    "missing_line_indexes": absent}})
            CustomerUsageInvoice.objects.filter(id=rec.id, status=USAGE_INVOICE_STATUS_PUSHING).update(
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
        existing = {} if created else PostpaidUsageService._list_invoice_items(inv.id, connected, api_key)
        items = []
        for i, label, cents, orig_micros in cent_lines:
            prior_item = existing.get(str(i))
            if prior_item is not None:
                items.append((label, orig_micros, prior_item.id))
                continue
            desc = f"Usage {period_start:%Y-%m}" + (f" — {label}" if label else "")
            item = stripe_call(
                stripe.InvoiceItem.create, api_key=api_key, retryable=True,
                idempotency_key=f"usage-item-{rec.id}{gen}-{i}",
                customer=owner.stripe_customer_id, invoice=inv.id, amount=cents,
                currency=currency, description=desc, stripe_account=connected,
                metadata={"usage_invoice_id": str(rec.id), "line_index": str(i)})
            items.append((label, orig_micros, item.id))
        CustomerUsageInvoice.objects.filter(id=rec.id, status=USAGE_INVOICE_STATUS_PUSHING).update(
            push_phase="items_pinned")
        stripe_call(
            stripe.Invoice.finalize_invoice, api_key=api_key, retryable=True,
            idempotency_key=f"usage-finalize-{rec.id}{gen}", invoice=inv.id,
            auto_advance=True, stripe_account=connected)
        CustomerUsageInvoice.objects.filter(id=rec.id, status=USAGE_INVOICE_STATUS_PUSHING).update(
            push_phase="finalized")
        return inv.id, items, residual

    @staticmethod
    def _resolve_consolidation_target(tenant, owner, rec, connected, api_key):
        """F5.5 target resolution: the owner's subscription-renewal DRAFT, if
        usage can still safely ride it. Returns the Stripe invoice or None
        (standalone fallback).

        Stripe auto-finalizes a renewal draft ~1h after the cycle anchor.
        Pinning items into a draft that finalizes mid-push forks into the
        safety addendum's split path, so a draft already past
        CONSOLIDATION_MAX_DRAFT_AGE_SECONDS (or one we cannot age, or one that
        will never auto-advance) is treated as a missed window and the push
        falls back to the standalone invoice it fully controls.
        """
        from apps.subscriptions.ports import get_active_subscription_for_consolidation

        sub = get_active_subscription_for_consolidation(tenant, owner)
        if not sub:
            logger.info("postpaid.consolidation_no_active_subscription", extra={"data": {
                "usage_invoice_id": str(rec.id), "customer_id": str(owner.id)}})
            return None
        result = stripe_call(
            stripe.Invoice.list, api_key=api_key,
            subscription=sub["stripe_subscription_id"], status="draft",
            stripe_account=connected, limit=10)
        draft = next(iter(result.auto_paging_iter()), None)
        draft_created = getattr(draft, "created", None) if draft is not None else None
        age = (timezone.now().timestamp() - draft_created) if draft_created else None
        if (draft is None or age is None
                or age > CONSOLIDATION_MAX_DRAFT_AGE_SECONDS
                or not getattr(draft, "auto_advance", False)):
            logger.warning("postpaid.consolidation_window_missed", extra={"data": {
                "usage_invoice_id": str(rec.id), "customer_id": str(owner.id),
                "stripe_subscription_id": sub["stripe_subscription_id"],
                "draft_invoice_id": getattr(draft, "id", None),
                "draft_age_seconds": int(age) if age is not None else None}})
            return None
        return draft

    @staticmethod
    def _push_consolidated(tenant, owner, rec, target, cent_lines, residual, gen,
                           connected, api_key, currency, period_start):
        """F5.5 SAFETY ADDENDUM: the target is the subscription renewal draft —
        Stripe finalizes it on ITS clock, regardless of our progress, so the
        F0.1 blind-adopt assumption (self-controlled finalization) NEVER
        applies here.

        - Target still draft: ensure OUR items (diffed by line_index, filtered
          to this rec's metadata — a renewal sweeps foreign pending items too)
          and stop. NO finalize call, ever: Stripe auto-finalizes the renewal.
        - Target finalized (open/paid/uncollectible): diff the frozen lines
          against what actually landed. All present -> adopt (record the
          renewal id). Some/none -> bill ONLY the missing lines on a fresh
          standalone remainder invoice we control, finalize it, and record
          THAT id (postpaid.consolidation_partial_split): every line lands on
          exactly one finalized invoice — no double-bill, no silent loss.
        """
        from apps.billing.invoicing.models import CustomerUsageInvoice

        # THE RENEWAL DRAFT IS STRIPE'S, IN THE SUBSCRIPTION'S CURRENCY, and a
        # line in another one cannot ride it (#565). A subscription a connected
        # account holds in a currency UBB never admitted is exactly that case,
        # so the push refuses here rather than sending a line Stripe would
        # either reject or bill in the wrong money.
        stated = getattr(target, "currency", None)
        if isinstance(stated, str):
            currency = the_rails_currency(
                f"usage invoice {rec.id}", currency,
                {f"Stripe invoice {target.id}": stated})

        target_status = getattr(target, "status", "")
        if target_status == "draft":
            existing = PostpaidUsageService._list_invoice_items(
                target.id, connected, api_key, usage_invoice_id=str(rec.id))
            items, finalized_under_us = [], False
            for i, label, cents, orig_micros in cent_lines:
                prior_item = existing.get(str(i))
                if prior_item is not None:
                    if getattr(prior_item, "amount", None) != cents:
                        # Alert-only: a recovered item whose cents diverge from
                        # the frozen line (e.g. a --rebill-void re-aggregation
                        # against a still-live draft target). The live item is
                        # what will bill; never double-pin next to it.
                        logger.error("postpaid.consolidated_item_amount_mismatch",
                                     extra={"data": {
                                         "usage_invoice_id": str(rec.id),
                                         "stripe_invoice_id": target.id,
                                         "line_index": str(i),
                                         "expected_cents": cents,
                                         "item_amount": getattr(prior_item, "amount", None)}})
                    items.append((label, orig_micros, prior_item.id))
                    continue
                desc = f"Usage {period_start:%Y-%m}" + (f" — {label}" if label else "")
                try:
                    item = stripe_call(
                        stripe.InvoiceItem.create, api_key=api_key, retryable=True,
                        idempotency_key=f"usage-item-{rec.id}{gen}-c{target.id}-{i}",
                        customer=owner.stripe_customer_id, invoice=target.id,
                        amount=cents, currency=currency, description=desc,
                        stripe_account=connected,
                        metadata={"usage_invoice_id": str(rec.id),
                                  "line_index": str(i), "consolidated": "true"})
                except StripeFatalError:
                    # The ~45-min pre-check narrows but cannot close the race:
                    # the draft may have auto-finalized under us, turning
                    # item-create into an invalid request. Re-read the target;
                    # a genuine finalize falls through to the split handling
                    # below, anything else re-raises (parks failed_permanent).
                    target = stripe_call(
                        stripe.Invoice.retrieve, api_key=api_key,
                        id=target.id, stripe_account=connected)
                    if getattr(target, "status", "") not in ("open", "paid", "uncollectible"):
                        raise
                    finalized_under_us = True
                    break
                items.append((label, orig_micros, item.id))
            if not finalized_under_us:
                CustomerUsageInvoice.objects.filter(id=rec.id, status=USAGE_INVOICE_STATUS_PUSHING).update(
                    push_phase="items_pinned")
                # NO finalize: Stripe auto-finalizes the renewal (~1h after anchor).
                return target.id, items, residual
            target_status = getattr(target, "status", "")

        if target_status not in ("open", "paid", "uncollectible"):
            logger.error("postpaid.stripe_invoice_unusable", extra={"data": {
                "usage_invoice_id": str(rec.id), "stripe_invoice_id": target.id,
                "stripe_status": target_status}})
            raise StripeFatalError(
                f"Consolidated Stripe invoice {target.id} for usage invoice {rec.id} "
                f"has unexpected status {target_status!r}")

        # FINALIZED target: diff the frozen cent_lines against what landed.
        present = PostpaidUsageService._list_invoice_items(
            target.id, connected, api_key, usage_invoice_id=str(rec.id))
        missing = [(i, label, cents, orig_micros)
                   for i, label, cents, orig_micros in cent_lines
                   if str(i) not in present]
        if not missing:
            # Full adopt: every line landed before the auto-finalize.
            items = [(label, orig_micros, present[str(i)].id)
                     for i, label, cents, orig_micros in cent_lines]
            CustomerUsageInvoice.objects.filter(id=rec.id, status=USAGE_INVOICE_STATUS_PUSHING).update(
                push_phase="finalized")
            return target.id, items, residual

        remainder_id, remainder_items = PostpaidUsageService._bill_remainder(
            tenant, owner, rec, target.id, missing, gen,
            connected, api_key, currency, period_start)
        items = []
        for i, label, cents, orig_micros in cent_lines:
            if str(i) in present:
                items.append((label, orig_micros, present[str(i)].id))
            else:
                items.append((label, orig_micros, remainder_items.get(str(i), "")))
        # Record the REMAINDER id: it is the invoice WE control and finalized.
        # The renewal's payment is tracked by its SubscriptionInvoice row; the
        # consolidated lines stay traceable via their per-item metadata and the
        # UsageInvoiceLineItem ids recorded from BOTH invoices.
        logger.error("postpaid.consolidation_partial_split", extra={"data": {
            "usage_invoice_id": str(rec.id), "customer_id": str(owner.id),
            "consolidated_invoice_id": target.id,
            "remainder_invoice_id": remainder_id,
            "consolidated_line_indexes": sorted(present.keys()),
            "remainder_line_indexes": [str(i) for i, label, cents, orig_micros in missing]}})
        CustomerUsageInvoice.objects.filter(id=rec.id, status=USAGE_INVOICE_STATUS_PUSHING).update(
            push_phase="finalized")
        return remainder_id, items, residual

    @staticmethod
    def _bill_remainder(tenant, owner, rec, target_id, missing, gen,
                        connected, api_key, currency, period_start):
        """The split's standalone remainder: create-or-resume OUR invoice, pin
        ONLY the lines the auto-finalized consolidated target missed, and
        finalize it (we control this one). Every idempotency key is namespaced
        by the target id (-r{target}) and carries the generation, so neither a
        later generation nor a fresh target can ever replay these keys.
        Returns ``(invoice_id, {line_index: item_id})``.
        """
        inv = PostpaidUsageService._find_existing_invoice(rec, owner, connected, api_key)
        created = False
        if inv is None:
            extra = {}
            if tenant.automatic_tax_enabled:
                extra["automatic_tax"] = {"enabled": True}
            inv = stripe_call(
                stripe.Invoice.create, api_key=api_key, retryable=True,
                idempotency_key=f"usage-invoice-{rec.id}{gen}-r{target_id}",
                customer=owner.stripe_customer_id, auto_advance=False,
                stripe_account=connected,
                metadata={"usage_invoice_id": str(rec.id), "tenant_id": str(tenant.id),
                          "period_start": period_start.isoformat(),
                          "consolidated_remainder_of": target_id},
                **extra)
            created = True
        inv_status = "draft" if created else getattr(inv, "status", "")
        if inv_status in ("open", "paid", "uncollectible"):
            # A prior split attempt already finalized the remainder — adopt it.
            existing = PostpaidUsageService._list_invoice_items(inv.id, connected, api_key)
            return inv.id, {str(i): (existing[str(i)].id if str(i) in existing else "")
                            for i, label, cents, orig_micros in missing}
        if inv_status != "draft":
            logger.error("postpaid.stripe_invoice_unusable", extra={"data": {
                "usage_invoice_id": str(rec.id), "stripe_invoice_id": inv.id,
                "stripe_status": inv_status}})
            raise StripeFatalError(
                f"Remainder Stripe invoice {inv.id} for usage invoice {rec.id} has "
                f"unexpected status {inv_status!r}")
        existing = {} if created else PostpaidUsageService._list_invoice_items(
            inv.id, connected, api_key)
        out = {}
        for i, label, cents, orig_micros in missing:
            prior_item = existing.get(str(i))
            if prior_item is not None:
                out[str(i)] = prior_item.id
                continue
            desc = f"Usage {period_start:%Y-%m}" + (f" — {label}" if label else "")
            item = stripe_call(
                stripe.InvoiceItem.create, api_key=api_key, retryable=True,
                idempotency_key=f"usage-item-{rec.id}{gen}-r{target_id}-{i}",
                customer=owner.stripe_customer_id, invoice=inv.id, amount=cents,
                currency=currency, description=desc, stripe_account=connected,
                metadata={"usage_invoice_id": str(rec.id), "line_index": str(i)})
            out[str(i)] = item.id
        stripe_call(
            stripe.Invoice.finalize_invoice, api_key=api_key, retryable=True,
            idempotency_key=f"usage-finalize-{rec.id}{gen}-r{target_id}", invoice=inv.id,
            auto_advance=True, stripe_account=connected)
        return inv.id, out

    @staticmethod
    def _find_existing_invoice(rec, owner, connected, api_key):
        """I4 belt-and-braces: before any create, deterministically look for an
        invoice already minted for this row. Invoice.list + client-side metadata
        match (Invoice.search has freshness lag). Skips void invoices so a
        deliberately-voided invoice can be replaced (--rebill-void)."""
        created_gte = int((rec.created_at - timedelta(days=1)).timestamp())
        result = stripe_call(
            stripe.Invoice.list, api_key=api_key, customer=owner.stripe_customer_id,
            stripe_account=connected, created={"gte": created_gte}, limit=100)
        for inv in result.auto_paging_iter():
            if getattr(inv, "status", "") == "void":
                continue
            # A real Invoice's metadata is a StripeObject, not a dict (F-3a):
            # the dict-style read here raised on the first push whenever the
            # owner had any non-void invoice in the lookback.
            if metadata_value(inv, "usage_invoice_id") == str(rec.id):
                return inv
        return None

    @staticmethod
    def _list_invoice_items(invoice_id, connected, api_key, usage_invoice_id=None):
        """Items already pinned to the invoice, indexed by their line_index metadata.
        Legacy items without metadata are unindexable (blank item-id fallback).
        F5.5: pass usage_invoice_id on a CONSOLIDATED target — the renewal
        carries foreign items too, so only items stamped with this rec's
        metadata may be indexed (a foreign line_index must never shadow ours)."""
        result = stripe_call(
            stripe.InvoiceItem.list, api_key=api_key,
            invoice=invoice_id, stripe_account=connected, limit=100)
        indexed = {}
        for item in result.auto_paging_iter():
            # A real InvoiceItem's metadata is a StripeObject, not a dict (F-3a).
            if (usage_invoice_id is not None
                    and metadata_value(item, "usage_invoice_id") != usage_invoice_id):
                continue
            line_index = metadata_value(item, "line_index")
            if line_index is not None:
                indexed[line_index] = item
        return indexed
