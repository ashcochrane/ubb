import logging

from core.exceptions import NegativeKnownPriceRefused
from apps.platform.events.schemas import CustomerDeleted, UsageRecorded
from apps.platform.tenants.models import Tenant
from apps.billing.tenant_billing.services import TenantBillingService
from core.vocabulary import USAGE_EVENT_KIND_METERED_USAGE

logger = logging.getLogger("ubb.events")


def handle_usage_recorded_billing(event_id, payload):
    """Outbox handler: draw the usage down against the owner's wallet.

    Registered as outbox handler with requires_product="billing".
    Called by the outbox dispatcher with (event_id, payload) signature.

    The wallet movement and its whole winning-branch tail — exactly-once
    debit, lot consumption, WalletBalanceOverage on zero-cross, the #39/#40
    floor-crossing lanes (or the Tier-1 suspension when enforcement is off),
    and WalletBalanceLow under the auto-top-up trigger — live behind the wallet
    seam (``wallet_ops.draw_down_usage``, #109). This handler keeps what is
    caller-side by decision 7: the postpaid branch, the owner resolution,
    billing-period accumulation, and the spend-pool counters.

    This handler NEVER calls Stripe or dispatches payment tasks.
    Payment connectors subscribe to the emitted events.
    """
    evt = UsageRecorded.from_payload(payload)
    tenant = Tenant.objects.get(id=evt.tenant_id)
    billed_cost_micros = evt.cost_micros

    # ⚠ `None > 0` IS A `TypeError`, AND THIS IS AN OUTBOX HANDLER (#351). The
    # comparison read the payload's legacy billed field, which was typed `int`
    # while the column filling it went nullable — so the first posting UBB could
    # not price would have taken this handler down, and an outbox handler that
    # raises retries with backoff rather than failing a request. Nothing in
    # the priced branch below applies to an event with no resolved price:
    # there is no amount to draw down and none to count towards the owner's
    # live spend. The PERIOD still counts it (#563): an unpriced event is an
    # event the tenant recorded, and only its money is absent.
    #
    # ⚠ AND THE `> 0` THAT RODE WITH IT IS GONE (#603 ruling 9). It was a
    # 2026-02 missing-value guard with no sign reason (`6069675803` §A), and it
    # made a known ZERO price "no money": the period's event count missed it
    # until the close rewrote the total with a drift warning. A known price is
    # never negative — a negative one is `unknown` with its reason, so it
    # stops at the line above — and a known zero is a real price: it is
    # COUNTED below, and it moves no money because there is none to move.
    #
    # A NEGATIVE ONE ARRIVING ANYWAY IS REFUSED BY NAME, never absorbed: the
    # old guard dropped it silently, and taking it would credit a wallet —
    # negative money on the rails, which v1 does not carry (ADR-0020 §5).
    if billed_cost_micros is not None and billed_cost_micros < 0:
        raise NegativeKnownPriceRefused(evt.event_id, "the billing rails")
    # WHAT THIS POSTING IS, read once from the canonical `Posting.kind`
    # (#563; the owner's §0.4 D). The payload deliberately carries no kind
    # (`charge_projection.py`), and nothing else may stand in for one — not
    # the pricing status, not a Task link: metered usage recorded against a
    # running unit of work carries a Task too. The period counts every
    # metered event, priced or not, and never a Task Charge, whose money it
    # keeps; the mechanism a stop records is read off the same kind.
    from apps.metering.queries import get_posting_kind
    kind = get_posting_kind(evt.event_id)
    counts_as_event = kind == USAGE_EVENT_KIND_METERED_USAGE
    if billed_cost_micros is None:
        TenantBillingService.accumulate_usage(
            tenant, None, counts_as_event=counts_as_event)
    else:
        from apps.platform.customers.models import Customer
        seat = Customer.objects.get(id=evt.customer_id)
        mechanism = _the_mechanism_for(kind)
        # Postpaid has no wallet to draw down. The pool's stop/suspension —
        # in every mode since #459 — rides the StopSignalState transition
        # guard from the fast lane at the crossing, the seat-level compare in
        # the shared tail below, and the hourly reconcile's SET power; this
        # handler never reads the stop flag (the old D13 shape), so a stop
        # and its suspension cannot double-fire.
        #
        # A ZERO DRAWS NOTHING DOWN: there is no amount to debit and no
        # ledger row to write for it, which is also what drawdown repair's
        # `iter_billable_postings` selects on — the two agree on what a
        # drawdown is owed for.
        if tenant.billing_mode != "postpaid" and billed_cost_micros != 0:
            from apps.billing.wallets import operations as wallet_ops

            owner_id = evt.billing_owner_id or str(seat.resolve_billing_owner().id)
            usage_event_id = evt.event_id
            # The whole drawdown — lock, lazy expiry, exactly-once debit, lot
            # consumption, and the winning-branch tail (WalletBalanceOverage, the
            # #39/#40 crossing lanes or the Tier-1 suspension, WalletBalanceLow) —
            # lives behind the wallet seam (#109).
            wallet_ops.draw_down_usage(
                customer_id=owner_id, tenant=tenant,
                usage_event_id=usage_event_id,
                billed_cost_micros=billed_cost_micros,
                trigger_source=mechanism)

        # Shared tail — control + attribution stay on the SEAT:
        TenantBillingService.accumulate_usage(
            tenant, billed_cost_micros, counts_as_event=counts_as_event)
        # Pool policy, the SEAT level (slice 6 §4): the seat's counter is
        # incremented once per posting in EVERY mode — a delivered
        # fixed-price unit's Charge reaches this tail as one posting and is
        # counted exactly once — and the pool service compares it against
        # the seat's pool on the durable lane (#459).
        # A pool is EFFECTIVE-month basis; the live Redis
        # counter tracks the CURRENT wall-clock month only. A backdated event
        # whose effective month is a PRIOR month must NOT inflate this month's
        # counter (the hourly reconcile_customer_spend_pool_counters rebuild — already
        # effective_at-filtered via get_customer_cost_totals — is the source
        # of truth). Absent/unparseable effective_at = legacy payload =
        # current behavior (increment).
        # Documented enforcement bypass: an enforcing-capped seat can backdate
        # usage into the prior month to evade the live cap. The exposure is
        # bounded by Tenant.backfill_window_days (0..60); tenants needing
        # airtight caps set it low — 0 disables backfill entirely.
        from django.utils import timezone as _tz
        from django.utils.dateparse import parse_datetime
        from core.crossing import same_month
        count_in_live = True
        raw_eff = evt.effective_at
        if raw_eff:
            eff = parse_datetime(raw_eff)
            if eff is not None:
                count_in_live = same_month(eff, _tz.now())
        if count_in_live:
            from apps.billing.gating.services.customer_spend_pool_service import (
                CustomerSpendPoolService)
            CustomerSpendPoolService.record_usage_spend(
                seat, billed_cost_micros, trigger_source=mechanism)


def _the_mechanism_for(kind):
    """The mechanism a stop this drawdown opens records (#569), read off the
    posting's kind because the payload deliberately carries none: a
    delivered fixed-price unit's Charge is the projection's
    (`charge_projection` — closing work as delivered, not a usage report),
    and every other posting is a usage report's (`usage_ingest`, whichever
    lane — the live debit or this drawdown — finds its crossing). One
    mechanism value for the projection, never a cause: the cause stays the
    floor's or the Pool's word."""
    from core.vocabulary import (TRIGGER_SOURCE_CHARGE_PROJECTION,
                                 TRIGGER_SOURCE_USAGE_INGEST,
                                 USAGE_EVENT_KIND_TASK_CHARGE)
    if kind == USAGE_EVENT_KIND_TASK_CHARGE:
        return TRIGGER_SOURCE_CHARGE_PROJECTION
    return TRIGGER_SOURCE_USAGE_INGEST


def handle_customer_deleted_billing(event_id, payload):
    """Outbox handler: clean up billing resources when customer is deleted.

    Registered as outbox handler with requires_product="billing".
    Soft-deletes Wallet and AutoTopUpConfig for the customer.
    """
    customer_id = CustomerDeleted.from_payload(payload).customer_id

    from apps.billing.wallets.models import Wallet
    from apps.billing.topups.models import AutoTopUpConfig

    try:
        Wallet.objects.get(customer_id=customer_id).soft_delete()
    except Wallet.DoesNotExist:
        pass
    try:
        AutoTopUpConfig.objects.get(customer_id=customer_id).soft_delete()
    except AutoTopUpConfig.DoesNotExist:
        pass
