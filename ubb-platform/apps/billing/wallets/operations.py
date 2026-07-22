"""wallet_ops — the Wallet operations module (#109).

The ledger state machine for EVERY wallet mutation lives here, behind named
per-op functions over one private executor, so the skeleton

    lock -> lazy expiry -> replay probe -> mutate -> live-counter mirror
         -> winning-branch events

exists in exactly one spine. Callers (the api/v1 handlers, the usage-recorded
outbox handler, the drawdown repair beat, the top-up credit paths, the Stripe
clawback webhooks, the expiry sweep) translate their transport and call; no
caller writes ``Wallet.balance_micros``, creates a ``WalletTransaction`` /
``CreditGrant``, or imports ``GrantLedger`` — the perimeter walker in
``apps/billing/tests/test_wallet_perimeter.py`` pins that.

Design decisions (grilled 2026-07-22, recorded on issue #109):

- **Refused results, not exceptions.** Every op returns an ``OpResult`` with
  ``outcome: applied | replayed | refused | noop``; refusals carry a code plus
  the numbers handlers need. Semantic, not taste: a refusal must still COMMIT
  the lazy-expiry side effects it triggered (the refusal body quotes the
  post-expiry balance) — an exception raised inside the module's atomic would
  roll them back.
- **The module owns the mirror.** The executor derives the Tier-2 live-counter
  credit from the op's balance delta and registers the single
  ``transaction.on_commit(LiveLedgerService.credit)`` for POSITIVE deltas only
  (mandatory — the MIN-merge reconcile cannot re-raise a missed credit;
  a missed debit is absorbed by the MIN-merge, so debits never mirror).
- **Audit is a caller-passed value.** ``Audit`` (actor, reason_code,
  reference, description) is stamped onto the ledger row atomically with the
  money movement; automated paths pass nothing. The platform audit ledger
  (ADR-004 ``audit_record``) stays with the HTTP handlers, gated on
  ``outcome == "applied"`` inside the caller's co-commit transaction.
- **Co-commit callers wrap an outer transaction.** Django atomics nest: a
  top-up caller opens ``transaction.atomic()``, calls ``credit_top_up``, then
  locks + saves the ``TopUpAttempt`` keyed on ``outcome == "applied"`` — one
  commit, wallet→attempt lock order preserved. This is THE pattern for
  callers that must co-commit rows with the money movement.
- **Per-op expiry placement is parity-preserved**: ``credit``, ``mint_grant``
  and ``credit_top_up`` do NOT run lazy expiry (they never did); every
  consuming/debiting op expires due lots before reading the balance.
- **Events are module-emitted, winning branch only** (never on replay or
  refusal). The drawdown tail (``BalanceOverage`` on zero-cross, the #39
  floor-stop transition, Tier-1 suspension when enforcement is off,
  ``BalanceLow`` under the top-up trigger) is suppressed by the ``repair``
  flag (I12: a back-correction never re-fires signals). Caller-side and
  staying there: the postpaid branch, ``TenantBillingService.accumulate_usage``
  and the budget counters.

``GrantLedger`` (grants.py) is private implementation of this module.
"""
import logging
from dataclasses import dataclass

from django.db import IntegrityError, transaction

logger = logging.getLogger("ubb.billing")

# Refusal codes (decision 3). Handlers map these to their HTTP problems.
WOULD_OVERDRAW = "would_overdraw"
INSUFFICIENT_WITHDRAWABLE = "insufficient_withdrawable"
USAGE_EVENT_NOT_FOUND = "usage_event_not_found"
IDEMPOTENCY_CONFLICT = "idempotency_conflict"
GRANT_NOT_FOUND = "grant_not_found"


@dataclass(frozen=True)
class Audit:
    """Caller-supplied attribution stamped onto the ledger row atomically with
    the money movement. Automated paths pass nothing (the defaults)."""
    actor: str = ""
    reason_code: str = ""
    reference: str = ""
    description: str = ""


_NO_AUDIT = Audit()


@dataclass(frozen=True)
class OpResult:
    """What every wallet op returns.

    outcome:
      applied  — this call moved money (the winning branch; events fired).
      replayed — the idempotency key already has a ledger row; nothing moved.
      refused  — a money rule said no; ``refusal_code`` says which. Any lazy
                 expiry this op triggered still COMMITS (decision 3).
      noop     — nothing to do (e.g. voiding a grant that is no longer active).

    balance_micros is the wallet balance AFTER the op (post-expiry on a
    refusal). ``reference_id`` is the (replayed) ledger row's reference — the
    refund replay quirk: a replayed refund answers with the ORIGINAL
    ``reference_id`` as its refund id. ``amount_micros`` is the applied move's
    signed delta (None unless applied)."""
    outcome: str
    balance_micros: int
    transaction_id: str | None = None
    reference_id: str = ""
    amount_micros: int | None = None
    refusal_code: str | None = None
    floor_micros: int | None = None
    grant: object | None = None


@dataclass
class _Move:
    """The mutation an op decided to make (built by its ``prepare``)."""
    txn_type: str
    amount_micros: int  # signed delta on the wallet balance
    description: str
    reference_id: str = ""
    usage_event_id: object = None
    reason_code: str = ""
    actor: str = ""
    mint: object = None    # fn(wallet, txn) — same-savepoint lot creation
    settle: object = None  # fn(wallet, txn) — post-balance grant bookkeeping
    events: object = None  # fn(wallet, owner, old, new, txn) — winning branch only
    result: object = None  # fn(wallet, txn) -> OpResult, else the default shape


def _execute(*, customer_id, tenant, key, run_expiry, prepare, on_replay,
             on_conflict=None, pre=None):
    """The one spine every op runs through.

    lock -> [pre] -> [lazy expiry] -> replay probe -> prepare (money rules)
         -> savepoint ledger write (+ same-savepoint mint) -> balance save
         -> grant settle -> mirror (positive deltas only) -> events -> result

    The probe-first + savepoint-backstop pair is the unified exactly-once
    machinery: the probe answers replays under the wallet lock; the savepoint
    (I2) only strengthens races that slip past it. ``on_conflict`` shapes the
    raced-replay result (defaults to a bare ``replayed``).
    """
    from apps.billing.locking import lock_for_billing
    from apps.billing.wallets.grants import GrantLedger
    from apps.billing.wallets.models import WalletTransaction

    with transaction.atomic():
        wallet, owner = lock_for_billing(customer_id)
        if pre is not None:
            early = pre(wallet)
            if early is not None:
                return early
        if run_expiry:
            GrantLedger.expire_due(wallet)
        existing = WalletTransaction.objects.filter(
            wallet=wallet, idempotency_key=key).first()
        if existing is not None:
            return on_replay(wallet, existing)
        move = prepare(wallet, owner)
        if isinstance(move, OpResult):
            return move  # refused / noop — commits any expiry side effects
        old_balance = wallet.balance_micros
        new_balance = old_balance + move.amount_micros
        try:
            with transaction.atomic():  # savepoint: I2 exactly-once backstop
                txn = WalletTransaction.objects.create(
                    wallet=wallet,
                    transaction_type=move.txn_type,
                    amount_micros=move.amount_micros,
                    balance_after_micros=new_balance,
                    description=move.description,
                    reference_id=move.reference_id,
                    idempotency_key=key,
                    usage_event_id=move.usage_event_id or None,
                    reason_code=move.reason_code,
                    actor=move.actor,
                )
                if move.mint is not None:
                    move.mint(wallet, txn)
        except IntegrityError:
            if on_conflict is not None:
                return on_conflict(wallet)
            return OpResult(outcome="replayed", balance_micros=wallet.balance_micros)
        wallet.balance_micros = new_balance
        wallet.save(update_fields=["balance_micros", "updated_at"])
        if move.settle is not None:
            move.settle(wallet, txn)
        if move.amount_micros > 0:
            # THE mirror rule (Tier-2 P2/D20): every credit is mirrored onto
            # the live balance after commit — mandatory, the MIN-merge cannot
            # re-raise a missed credit. Debits are absorbed by the MIN-merge
            # and never mirror. Enforced here once, for every op.
            from apps.billing.gating.services.live_ledger_service import LiveLedgerService
            transaction.on_commit(
                lambda oid=wallet.customer_id, t=tenant, amt=move.amount_micros:
                LiveLedgerService.credit(oid, t, amt))
        if move.events is not None:
            move.events(wallet, owner, old_balance, new_balance, txn)
        if move.result is not None:
            return move.result(wallet, txn)
        return OpResult(outcome="applied", balance_micros=wallet.balance_micros,
                        transaction_id=str(txn.id), amount_micros=move.amount_micros)


def _replayed(wallet, existing):
    """Default replay shape: the stored row answers, nothing moves."""
    return OpResult(outcome="replayed", balance_micros=wallet.balance_micros,
                    transaction_id=str(existing.id),
                    reference_id=existing.reference_id)


# ---------------------------------------------------------------------------
# Manual money movement (the /debit /credit /withdraw /refund handlers)
# ---------------------------------------------------------------------------


def debit(*, customer_id, tenant, amount_micros, idempotency_key,
          allow_negative=False, audit=_NO_AUDIT):
    """Hand-moved debit. Respects the overdraft floor unless forced
    (``allow_negative`` logs ``forced_overdraw``). Mirrors the drawdown gate —
    non-postpaid only; postpaid balances are meant to go negative."""
    def prepare(wallet, owner):
        from apps.billing.wallets.grants import GrantLedger

        new_balance = wallet.balance_micros - amount_micros
        if tenant.billing_mode != "postpaid":
            from apps.billing.queries import get_customer_min_balance
            from apps.billing.gating.crossing import past_floor
            floor = get_customer_min_balance(wallet.customer_id, tenant.id)
            if past_floor(new_balance, floor):
                if not allow_negative:
                    return OpResult(
                        outcome="refused", balance_micros=wallet.balance_micros,
                        refusal_code=WOULD_OVERDRAW, floor_micros=floor)
                logger.warning("billing.forced_overdraw", extra={"data": {
                    "customer_id": str(wallet.customer_id),
                    "amount_micros": amount_micros,
                    "balance_before_micros": wallet.balance_micros,
                    "balance_after_micros": new_balance,
                    "floor_micros": floor, "reference": audit.reference}})

        def settle(wallet, txn):
            GrantLedger.allocate(wallet, txn, amount_micros)  # F4.3: usage order

        return _Move(txn_type="DEBIT", amount_micros=-amount_micros,
                     description=audit.description or "External debit",
                     reference_id=audit.reference,
                     reason_code=audit.reason_code, actor=audit.actor,
                     settle=settle)

    return _execute(customer_id=customer_id, tenant=tenant, key=idempotency_key,
                    run_expiry=True,  # F4.3 lazy expiry: never consume a due lot
                    prepare=prepare, on_replay=_replayed)


def credit(*, customer_id, tenant, amount_micros, idempotency_key,
           audit=_NO_AUDIT):
    """Credit the wallet with LEGACY BASE money (non-expiring, no grant lot).

    Deliberately untouched by F4.3: base is derived (balance minus active
    grant remainders), so an ADJUSTMENT credit simply grows base — and runs
    NO lazy expiry (it never did). Expiring/promo credit is ``mint_grant``.
    """
    def prepare(wallet, owner):
        return _Move(txn_type="ADJUSTMENT", amount_micros=amount_micros,
                     description=audit.description or "Credit",
                     reference_id=audit.reference,
                     reason_code=audit.reason_code, actor=audit.actor)

    return _execute(customer_id=customer_id, tenant=tenant, key=idempotency_key,
                    run_expiry=False, prepare=prepare, on_replay=_replayed)


def withdraw(*, customer_id, tenant, amount_micros, idempotency_key,
             audit=_NO_AUDIT):
    """Withdraw base + paid money. Promo credit is NOT withdrawable (F4.3):
    availability is balance minus active promo remainders."""
    def prepare(wallet, owner):
        from apps.billing.wallets.grants import GrantLedger

        if wallet.balance_micros - GrantLedger.promo_remaining(wallet) < amount_micros:
            return OpResult(outcome="refused", balance_micros=wallet.balance_micros,
                            refusal_code=INSUFFICIENT_WITHDRAWABLE)

        def settle(wallet, txn):
            GrantLedger.allocate(wallet, txn, amount_micros,
                                 exclude_promo=True, allocation_type="withdrawal")

        def events(wallet, owner, old, new, txn):
            from apps.platform.events.outbox import write_event
            from apps.platform.events.schemas import WithdrawalRequested
            write_event(WithdrawalRequested(
                tenant_id=str(tenant.id),
                customer_id=str(owner.id),
                amount_micros=amount_micros,
                transaction_id=str(txn.id),
                idempotency_key=idempotency_key,
            ))

        return _Move(txn_type="WITHDRAWAL", amount_micros=-amount_micros,
                     description=audit.description or "Withdrawal",
                     settle=settle, events=events)

    return _execute(customer_id=customer_id, tenant=tenant, key=idempotency_key,
                    run_expiry=True, prepare=prepare, on_replay=_replayed)


def refund_usage(*, customer_id, tenant, usage_event_id, idempotency_key,
                 reason=""):
    """Refund a usage charge. The module looks the cost up via the sanctioned
    metering read channel (no caller supplies an amount, so no caller can book
    a wrong one), preserving replay-probe-before-lookup ordering. LOT-AWARE
    (F4.3): still-live funding lots are re-funded; the base remainder plus
    shares from since-expired/voided lots land as base credit."""
    def prepare(wallet, owner):
        from apps.billing.wallets.grants import GrantLedger
        from apps.billing.wallets.models import WalletTransaction
        from apps.metering.queries import get_usage_event_cost

        cost = get_usage_event_cost(usage_event_id, tenant_id=tenant.id)
        if cost is None:
            return OpResult(outcome="refused", balance_micros=wallet.balance_micros,
                            refusal_code=USAGE_EVENT_NOT_FOUND)

        def settle(wallet, txn):
            # F4.3 lot-aware re-fund: find the original deduction via its
            # pinned usage_event_id column and restore its GrantAllocation
            # slices into the still-live lots.
            original = WalletTransaction.objects.filter(
                wallet=wallet, transaction_type="USAGE_DEDUCTION",
                usage_event_id=usage_event_id,
            ).first()
            GrantLedger.refund(wallet, original)

        def events(wallet, owner, old, new, txn):
            from apps.platform.events.outbox import write_event
            from apps.platform.events.schemas import RefundRequested
            write_event(RefundRequested(
                tenant_id=str(tenant.id),
                customer_id=str(owner.id),
                usage_event_id=str(usage_event_id),
                refund_amount_micros=cost,
                reason=reason,
                idempotency_key=idempotency_key,
            ))

        return _Move(txn_type="REFUND", amount_micros=cost,
                     description=f"Refund: {usage_event_id}",
                     reference_id=str(usage_event_id),
                     settle=settle, events=events)

    return _execute(customer_id=customer_id, tenant=tenant, key=idempotency_key,
                    run_expiry=True,  # a due lot expires first, so its share
                    # of the refund correctly lands as base.
                    prepare=prepare, on_replay=_replayed)


# ---------------------------------------------------------------------------
# Credit grants (F4.3)
# ---------------------------------------------------------------------------


def mint_grant(*, customer_id, tenant, kind, amount_micros, expires_at,
               idempotency_key, audit=_NO_AUDIT):
    """Create an expiring (or non-expiring) credit grant lot on the billing
    owner's wallet. Exactly-once via ``grant:{idempotency_key}`` — the GRANT
    ledger row and the CreditGrant share one savepoint. A replayed key that
    belongs to a non-grant row refuses with ``idempotency_conflict``."""
    key = f"grant:{idempotency_key}"

    def replay_shape(wallet, existing):
        from apps.billing.wallets.models import CreditGrant
        grant = CreditGrant.objects.filter(source_transaction=existing).first()
        if grant is None:
            return OpResult(outcome="refused", balance_micros=wallet.balance_micros,
                            refusal_code=IDEMPOTENCY_CONFLICT)
        return OpResult(outcome="replayed", balance_micros=wallet.balance_micros,
                        transaction_id=str(existing.id), grant=grant)

    def on_conflict(wallet):
        from apps.billing.wallets.models import WalletTransaction
        existing = WalletTransaction.objects.get(wallet=wallet, idempotency_key=key)
        return replay_shape(wallet, existing)

    def prepare(wallet, owner):
        from apps.billing.wallets.grants import GrantLedger

        state = {}

        def mint(wallet, txn):
            state["grant"] = GrantLedger.create_grant(
                wallet, tenant.id, kind=kind, amount_micros=amount_micros,
                expires_at=expires_at, source="api",
                source_reference=idempotency_key, txn=txn)

        def result(wallet, txn):
            return OpResult(outcome="applied", balance_micros=wallet.balance_micros,
                            transaction_id=str(txn.id), amount_micros=amount_micros,
                            grant=state["grant"])

        return _Move(txn_type="GRANT", amount_micros=amount_micros,
                     description=audit.description or f"Credit grant ({kind})",
                     reference_id=idempotency_key, mint=mint, result=result)

    return _execute(customer_id=customer_id, tenant=tenant, key=key,
                    run_expiry=False, prepare=prepare,
                    on_replay=replay_shape, on_conflict=on_conflict)


def void_grant(*, customer_id, tenant, grant_id):
    """Void a grant: debit its remaining (clamped so the balance never goes
    negative, like expiry) and retire the lot. Exactly-once via
    ``grant_void:{grant_id}``; replays and no-longer-active lots return the
    lot unchanged with no ledger row."""
    key = f"grant_void:{grant_id}"
    state = {}

    def pre(wallet):
        from apps.billing.wallets.models import CreditGrant
        grant = CreditGrant.objects.filter(
            id=grant_id, wallet=wallet, tenant=tenant).first()
        if grant is None:
            return OpResult(outcome="refused", balance_micros=wallet.balance_micros,
                            refusal_code=GRANT_NOT_FOUND)
        state["grant"] = grant
        return None

    def lot_unchanged(wallet, _existing=None):
        grant = state["grant"]
        grant.refresh_from_db()
        return OpResult(outcome="replayed", balance_micros=wallet.balance_micros,
                        grant=grant)  # no txn: parity with the pre-seam replay

    def prepare(wallet, owner):
        grant = state["grant"]
        grant.refresh_from_db()  # expire_due may have just retired it
        if grant.status != "active":
            return OpResult(outcome="noop", balance_micros=wallet.balance_micros,
                            grant=grant)
        # Clamp like expiry (G3): voiding never drives the balance negative.
        debit_micros = min(grant.remaining_micros, max(wallet.balance_micros, 0))

        def settle(wallet, txn):
            # += (not =): a partial clawback may already have moved some of
            # this lot into voided_micros — voiding must accumulate.
            grant.voided_micros += grant.remaining_micros
            grant.remaining_micros = 0
            grant.status = "voided"
            grant.save(update_fields=[
                "voided_micros", "remaining_micros", "status", "updated_at"])

        def result(wallet, txn):
            return OpResult(outcome="applied", balance_micros=wallet.balance_micros,
                            transaction_id=str(txn.id),
                            amount_micros=-debit_micros, grant=grant)

        return _Move(txn_type="GRANT_VOID", amount_micros=-debit_micros,
                     description=f"Credit grant voided ({grant.kind})",
                     reference_id=str(grant.id), settle=settle, result=result)

    return _execute(customer_id=customer_id, tenant=tenant, key=key,
                    run_expiry=True,  # a due lot expires; the void then no-ops
                    pre=pre, prepare=prepare,
                    on_replay=lot_unchanged, on_conflict=lot_unchanged)


# ---------------------------------------------------------------------------
# Usage drawdown (live + repair — one code path, a repair flag)
# ---------------------------------------------------------------------------


def draw_down_usage(*, customer_id, tenant, usage_event_id, billed_cost_micros,
                    repair=False):
    """Deduct one usage event from the owner's wallet, exactly-once via
    ``usage_deduction:{usage_event_id}``.

    ``repair=False`` (the live outbox handler) runs the winning-branch tail:
    ``BalanceOverage`` on zero-cross, the #39 durable floor-stop lane (or the
    Tier-1 suspension when enforcement is off), the #40 soft-floor crossing,
    and ``BalanceLow`` under the auto-top-up trigger.

    ``repair=True`` (the reconcile beat) is the SAME path with the tail
    suppressed (I12: a back-correction never re-fires signals) and the
    reconciled description — repair twin ≡ live drawdown by construction.
    """
    key = f"usage_deduction:{usage_event_id}"

    def on_replay(wallet, existing):
        if existing.amount_micros != -billed_cost_micros:
            logger.error("ledger.usage_deduction_amount_mismatch", extra={"data": {
                "usage_event_id": str(usage_event_id),
                "existing": existing.amount_micros,
                "expected": -billed_cost_micros}})
        # I2: already debited -> no decrement, no events
        return OpResult(outcome="replayed", balance_micros=wallet.balance_micros,
                        transaction_id=str(existing.id))

    def prepare(wallet, owner):
        from apps.billing.wallets.grants import GrantLedger

        def settle(wallet, txn):
            # F4.3: winning branch only — lot consumption rides the
            # usage_deduction:{event_id} exactly-once key.
            GrantLedger.allocate(wallet, txn, billed_cost_micros)

        return _Move(
            txn_type="USAGE_DEDUCTION", amount_micros=-billed_cost_micros,
            description=(f"Usage (reconciled): {usage_event_id}" if repair
                         else f"Usage: {usage_event_id}"),
            reference_id=str(usage_event_id), usage_event_id=usage_event_id,
            settle=settle,
            events=None if repair else _drawdown_tail(tenant))

    return _execute(customer_id=customer_id, tenant=tenant, key=key,
                    run_expiry=True,  # F4.3: due lots expire BEFORE the
                    # balance read so this drawdown never consumes them.
                    prepare=prepare, on_replay=on_replay)


def _drawdown_tail(tenant):
    """The live drawdown's winning-branch signal tail (see draw_down_usage)."""
    def events(wallet, owner, old_balance, new_balance, txn):
        from apps.billing.queries import get_customer_min_balance
        from apps.billing.gating.crossing import crossed_floor, past_floor
        from apps.billing.topups.models import AutoTopUpConfig
        from apps.platform.events.outbox import write_event
        from apps.platform.events.schemas import (
            BalanceLow, BalanceOverage, CustomerSuspended)

        limit = get_customer_min_balance(owner.id, tenant.id)
        if old_balance >= 0 and new_balance < 0:   # I6
            # The zero-crossing EARLY WARNING (Stage D) — a distinct event,
            # deliberately NOT part of the #39 stop/resume pair.
            write_event(BalanceOverage(
                tenant_id=str(tenant.id), customer_id=str(owner.id),
                balance_micros=new_balance, overage_limit_micros=limit,
                overage_micros=-new_balance))
        from apps.platform.tenants.flags import enforcing
        if enforcing(tenant):
            # #39 §D — the DURABLE lane of the stop signal: a crossing of the
            # CONFIGURED floor drives the transition guard, independent of
            # Redis health (a crossing during a blind window signals late,
            # never lost). The winner emits stop.fired and performs the folded
            # suspension; a crossing the fast lane already signaled loses
            # silently. Signal bookkeeping must never poison the debit:
            # drive_stop is savepoint-isolated, and a failure here is
            # re-driven by the hourly reconcile.
            if crossed_floor(old_balance, new_balance, limit):
                from apps.platform.tasks.reasons import CUSTOMER_WIDE_STOP
                from apps.billing.gating.services.stop_signal_service import (
                    StopSignalService)
                from apps.billing.gating.services.live_ledger_service import (
                    LiveLedgerService)
                try:
                    StopSignalService.drive_stop(
                        owner.id, tenant, reason=CUSTOMER_WIDE_STOP,
                        balance_micros=new_balance)
                except Exception:
                    logger.warning("billing.floor_stop_transition_failed",
                                   extra={"data": {"owner_id": str(owner.id)}})
                LiveLedgerService.ensure_stop_flag(owner.id, CUSTOMER_WIDE_STOP)
            # #40 §F — the soft floor's ONLY crossing detector (no fast lane,
            # no Redis threshold: signal latency is outbox latency). Crossing
            # the resolved soft line drives the soft_floor family of the same
            # guard — the winner emits soft_floor.crossed. Never an ack
            # change, never a suspension; a drive lost here is re-announced by
            # the delivery patrol (#44), not by reconcile.
            from apps.billing.queries import get_customer_soft_min_balance
            soft = get_customer_soft_min_balance(owner.id, tenant.id)
            if crossed_floor(old_balance, new_balance, soft):
                from apps.billing.gating.services.stop_signal_service import (
                    StopSignalService)
                try:
                    StopSignalService.drive_soft_crossed(
                        owner.id, tenant, balance_micros=new_balance,
                        soft_min_balance_micros=soft)
                except Exception:
                    logger.warning("billing.soft_floor_transition_failed",
                                   extra={"data": {"owner_id": str(owner.id)}})
        elif past_floor(new_balance, limit) and owner.status == "active":
            # enforcement off: Tier-1 baseline suspension, byte-for-byte
            # (no signal suite, no ledger).
            owner.status = "suspended"
            owner.suspension_reason = "min_balance_exceeded"  # P6b/D15
            owner.save(update_fields=["status", "suspension_reason", "updated_at"])
            write_event(CustomerSuspended(
                tenant_id=str(tenant.id), customer_id=str(owner.id),
                reason="min_balance_exceeded", balance_micros=new_balance))
        try:
            config = AutoTopUpConfig.objects.get(customer=owner, is_enabled=True)
        except AutoTopUpConfig.DoesNotExist:
            config = None
        if config and new_balance < config.trigger_threshold_micros:
            write_event(BalanceLow(
                tenant_id=str(tenant.id), customer_id=str(owner.id),
                balance_micros=new_balance,
                threshold_micros=config.trigger_threshold_micros,
                suggested_topup_micros=config.top_up_amount_micros))
    return events


# ---------------------------------------------------------------------------
# Top-up credits (auto top-up + checkout webhook)
# ---------------------------------------------------------------------------


def credit_top_up(*, customer_id, tenant, amount_micros, idempotency_key,
                  source, source_reference, description, reference_id=""):
    """Credit a paid top-up: the TOP_UP ledger row and its PAID CreditGrant
    lot land in one savepoint, so the lot inherits exactly-once from the
    caller's key (``auto_topup:{pi}`` / ``topup:{session}``) with zero changes
    to the convergent callers. Expiry comes from the owner's
    ``CustomerBillingProfile.topup_grant_expiry_days`` (NULL = never expires).

    Co-commit callers (attempt status walks) wrap an outer
    ``transaction.atomic()`` and key their writes on ``outcome == "applied"``.
    """
    def prepare(wallet, owner):
        from apps.billing.wallets.grants import GrantLedger

        def mint(wallet, txn):
            GrantLedger.create_grant(
                wallet, tenant.id, kind="paid", amount_micros=amount_micros,
                expires_at=GrantLedger.topup_grant_expires_at(wallet.customer_id),
                source=source, source_reference=source_reference, txn=txn)

        return _Move(txn_type="TOP_UP", amount_micros=amount_micros,
                     description=description, reference_id=reference_id,
                     mint=mint)

    return _execute(customer_id=customer_id, tenant=tenant, key=idempotency_key,
                    run_expiry=False, prepare=prepare, on_replay=_replayed)


# ---------------------------------------------------------------------------
# Stripe clawbacks (dispute lost / charge refunded)
# ---------------------------------------------------------------------------


def claw_back_dispute(*, customer_id, tenant, amount_micros, dispute_id,
                      charge_id, attempt_id):
    """Deduct a lost dispute, exactly-once per dispute id, and restore G1 via
    the clawback cascade. The suspension reaction stays with the webhook
    caller (a Customer-status policy, not a wallet rule) off the returned
    balance."""
    return _claw_back(
        customer_id=customer_id, tenant=tenant, amount_micros=amount_micros,
        key=f"dispute:{dispute_id}", txn_type="DISPUTE_DEDUCTION",
        description=f"Dispute lost: {charge_id}", attempt_id=attempt_id)


def claw_back_stripe_refund(*, customer_id, tenant, amount_micros, refund_id,
                            attempt_id):
    """Deduct one Stripe-initiated refund, exactly-once per refund id (partial
    refunds arrive as separate events), and restore G1 via the cascade."""
    return _claw_back(
        customer_id=customer_id, tenant=tenant, amount_micros=amount_micros,
        key=f"stripe_refund:{refund_id}", txn_type="STRIPE_REFUND",
        description=f"Stripe refund: {refund_id}", attempt_id=attempt_id)


def _claw_back(*, customer_id, tenant, amount_micros, key, txn_type,
               description, attempt_id):
    def prepare(wallet, owner):
        from apps.billing.wallets.grants import GrantLedger
        from apps.billing.wallets.models import CreditGrant

        def settle(wallet, txn):
            # F4.3 clawback cascade (winning branch only): void the reversed
            # top-up's lot first, then consume other lots until G1 holds
            # again. Only top-up-born lots qualify as the source (an API/other
            # lot that happens to share the reference must never be voided for
            # a Stripe charge reversal); created_at order makes the pick
            # deterministic.
            source_grant = CreditGrant.objects.filter(
                wallet=wallet, source_reference=str(attempt_id),
                source__in=("checkout", "auto_topup"),
            ).order_by("created_at").first()
            GrantLedger.clawback(wallet, txn, amount_micros,
                                 source_grant=source_grant)

        return _Move(txn_type=txn_type, amount_micros=-amount_micros,
                     description=description, reference_id=str(attempt_id),
                     settle=settle)

    return _execute(customer_id=customer_id, tenant=tenant, key=key,
                    run_expiry=True,  # F4.3: due lots expire before the
                    # clawback reads them.
                    prepare=prepare, on_replay=_replayed)


# ---------------------------------------------------------------------------
# Expiry sweep + read rollup
# ---------------------------------------------------------------------------


def expire_due_sweep(customer_id, *, now=None):
    """Expire the customer's due grant lots under the wallet lock (the hourly
    beat's per-customer unit; lazy expiry in the money ops makes the beat a
    sweeper, not a correctness requirement). Returns the number of grants
    expired by THIS call."""
    from apps.billing.locking import lock_for_billing
    from apps.billing.wallets.grants import GrantLedger

    with transaction.atomic():
        wallet, _customer = lock_for_billing(customer_id)
        return GrantLedger.expire_due(wallet, now=now)


def balance_summary(wallet):
    """Read-only rollup for balance responses: active promo remaining, total
    remaining that can expire, and the soonest expiry."""
    from apps.billing.wallets.grants import GrantLedger

    return GrantLedger.balance_summary(wallet)
