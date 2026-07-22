"""#109 — the Wallet module's money rules, at the module interface.

The below-HTTP test surface for wallet mutations: refusals, replay quirks,
per-op expiry placement, the clawback cascade, the drawdown tail, and THE
mirror rule (every op, current and future, mirrors exactly its positive
balance delta — and nothing else). HTTP translation stays in the api/v1
endpoint tests; the perimeter itself is pinned by
apps/billing/tests/test_wallet_perimeter.py.
"""
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.utils import timezone

from apps.billing.wallets import operations as wallet_ops
from apps.billing.wallets.models import (
    CreditGrant, CustomerBillingProfile, GrantAllocation, Wallet,
    WalletTransaction,
)
from apps.billing.topups.models import AutoTopUpConfig
from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.platform.tenants.models import Tenant


def _tenant(**kw):
    kw.setdefault("name", "T")
    kw.setdefault("products", ["metering", "billing"])
    kw.setdefault("billing_mode", "prepaid")
    return Tenant.objects.create(**kw)


def _customer(tenant, external_id="c1"):
    return Customer.objects.create(tenant=tenant, external_id=external_id)


def _wallet(customer, balance=0):
    return Wallet.objects.create(customer=customer, balance_micros=balance)


def _mint(tenant, customer, *, kind="promo", amount=10_000_000, expires_at=None):
    """Mint a grant lot through the module itself (the real path)."""
    result = wallet_ops.mint_grant(
        customer_id=customer.id, tenant=tenant, kind=kind,
        amount_micros=amount, expires_at=expires_at,
        idempotency_key=str(uuid.uuid4()))
    assert result.outcome == "applied"
    return result.grant


def _txns(wallet, txn_type=None):
    qs = WalletTransaction.objects.filter(wallet=wallet)
    if txn_type:
        qs = qs.filter(transaction_type=txn_type)
    return qs


# ---------------------------------------------------------------------------
# THE mirror rule — decision 4: derived from the balance delta, one test for
# every op. A positive delta mirrors exactly that amount via
# LiveLedgerService.credit on commit; a non-positive delta never mirrors.
# ---------------------------------------------------------------------------


def _op_registry(tenant, customer, wallet):
    """(name, thunk, expected_mirror_micros_or_None) for EVERY public op."""
    event_id = uuid.uuid4()

    def seeded_refund():
        # A refund mirrors the looked-up cost: fake the metering read.
        with patch("apps.metering.queries.get_usage_event_cost",
                   return_value=2_000_000):
            return wallet_ops.refund_usage(
                customer_id=customer.id, tenant=tenant,
                usage_event_id=event_id, idempotency_key=str(uuid.uuid4()))

    # Minted OUTSIDE the mirror capture below: the mint itself mirrors. Large
    # enough that the sequence's earlier consuming ops leave it active.
    voidable = _mint(tenant, customer, kind="promo", amount=20_000_000)

    return [
        ("debit", lambda: wallet_ops.debit(
            customer_id=customer.id, tenant=tenant, amount_micros=1_000_000,
            idempotency_key=str(uuid.uuid4())), None),
        ("credit", lambda: wallet_ops.credit(
            customer_id=customer.id, tenant=tenant, amount_micros=3_000_000,
            idempotency_key=str(uuid.uuid4())), 3_000_000),
        ("withdraw", lambda: wallet_ops.withdraw(
            customer_id=customer.id, tenant=tenant, amount_micros=1_000_000,
            idempotency_key=str(uuid.uuid4())), None),
        ("refund_usage", seeded_refund, 2_000_000),
        ("mint_grant", lambda: wallet_ops.mint_grant(
            customer_id=customer.id, tenant=tenant, kind="promo",
            amount_micros=4_000_000, expires_at=None,
            idempotency_key=str(uuid.uuid4())), 4_000_000),
        ("void_grant", lambda: wallet_ops.void_grant(
            customer_id=customer.id, tenant=tenant, grant_id=voidable.id),
         None),
        ("draw_down_usage", lambda: wallet_ops.draw_down_usage(
            customer_id=customer.id, tenant=tenant,
            usage_event_id=str(uuid.uuid4()), billed_cost_micros=1_000_000),
         None),
        ("draw_down_usage[repair]", lambda: wallet_ops.draw_down_usage(
            customer_id=customer.id, tenant=tenant,
            usage_event_id=str(uuid.uuid4()), billed_cost_micros=1_000_000,
            repair=True), None),
        ("credit_top_up", lambda: wallet_ops.credit_top_up(
            customer_id=customer.id, tenant=tenant, amount_micros=5_000_000,
            idempotency_key=f"auto_topup:{uuid.uuid4()}", source="auto_topup",
            source_reference="att", description="Auto top-up"), 5_000_000),
        ("claw_back_dispute", lambda: wallet_ops.claw_back_dispute(
            customer_id=customer.id, tenant=tenant, amount_micros=1_000_000,
            dispute_id=str(uuid.uuid4()), charge_id="ch_1",
            attempt_id=uuid.uuid4()), None),
        ("claw_back_stripe_refund", lambda: wallet_ops.claw_back_stripe_refund(
            customer_id=customer.id, tenant=tenant, amount_micros=1_000_000,
            refund_id=str(uuid.uuid4()), attempt_id=uuid.uuid4()), None),
    ]


@pytest.mark.django_db
class TestMirrorRule:
    def test_every_op_mirrors_exactly_its_positive_delta(
            self, django_capture_on_commit_callbacks):
        """The five hand-wired credit-mirror sites died in #109; this is the
        one rule that replaced them. Credits mirror their amount; debits never
        mirror (the MIN-merge absorbs a missed debit but can never re-raise a
        missed credit)."""
        t = _tenant()
        c = _customer(t)
        _wallet(c, balance=50_000_000)
        for name, thunk, expected in _op_registry(t, c, None):
            with patch("apps.billing.gating.services.live_ledger_service."
                       "LiveLedgerService.credit") as credit:
                with django_capture_on_commit_callbacks(execute=True):
                    result = thunk()
            assert result.outcome == "applied", (name, result)
            if expected is None:
                assert not credit.called, f"{name} must not mirror"
            else:
                credit.assert_called_once_with(c.id, t, expected), name

    def test_registry_covers_every_public_op(self):
        """A new mutating op must join the registry above (and therefore the
        mirror rule) — this inventory check is what makes the rule bind
        'current and future'."""
        mutating = {
            "debit", "credit", "withdraw", "refund_usage", "mint_grant",
            "void_grant", "draw_down_usage", "credit_top_up",
            "claw_back_dispute", "claw_back_stripe_refund",
        }
        reads_and_sweeps = {"expire_due_sweep", "balance_summary"}
        import inspect
        public = {n for n in dir(wallet_ops)
                  if not n.startswith("_")
                  and inspect.isfunction(getattr(wallet_ops, n))
                  and getattr(wallet_ops, n).__module__ == wallet_ops.__name__}
        assert public - reads_and_sweeps == mutating, (
            "public op surface changed — add the new op to _op_registry with "
            "its expected mirror, and to the perimeter pin's vocabulary")

    def test_replay_and_refusal_never_mirror(
            self, django_capture_on_commit_callbacks):
        t = _tenant()
        c = _customer(t)
        _wallet(c, balance=10_000_000)
        key = str(uuid.uuid4())
        with django_capture_on_commit_callbacks(execute=True):
            wallet_ops.credit(customer_id=c.id, tenant=t,
                              amount_micros=1_000_000, idempotency_key=key)
        with patch("apps.billing.gating.services.live_ledger_service."
                   "LiveLedgerService.credit") as credit:
            with django_capture_on_commit_callbacks(execute=True):
                replay = wallet_ops.credit(customer_id=c.id, tenant=t,
                                           amount_micros=1_000_000,
                                           idempotency_key=key)
                refusal = wallet_ops.withdraw(
                    customer_id=c.id, tenant=t, amount_micros=99_000_000,
                    idempotency_key=str(uuid.uuid4()))
        assert replay.outcome == "replayed"
        assert refusal.outcome == "refused"
        assert not credit.called


# ---------------------------------------------------------------------------
# Refusals — refused results, not exceptions (decision 3)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestRefusals:
    def test_debit_refuses_below_the_floor_with_the_numbers(self):
        t = _tenant()
        c = _customer(t)
        _wallet(c, balance=5_000_000)
        result = wallet_ops.debit(customer_id=c.id, tenant=t,
                                  amount_micros=6_000_000,
                                  idempotency_key=str(uuid.uuid4()))
        assert result.outcome == "refused"
        assert result.refusal_code == wallet_ops.WOULD_OVERDRAW
        assert result.floor_micros == 0
        assert result.balance_micros == 5_000_000
        assert not _txns(Wallet.objects.get(customer=c)).exists()

    def test_forced_debit_overdraws_and_books(self):
        t = _tenant()
        c = _customer(t)
        w = _wallet(c, balance=5_000_000)
        result = wallet_ops.debit(customer_id=c.id, tenant=t,
                                  amount_micros=6_000_000,
                                  idempotency_key=str(uuid.uuid4()),
                                  allow_negative=True)
        assert result.outcome == "applied"
        w.refresh_from_db()
        assert w.balance_micros == -1_000_000

    def test_postpaid_debit_skips_the_floor(self):
        t = _tenant(billing_mode="postpaid")
        c = _customer(t)
        w = _wallet(c, balance=0)
        result = wallet_ops.debit(customer_id=c.id, tenant=t,
                                  amount_micros=2_000_000,
                                  idempotency_key=str(uuid.uuid4()))
        assert result.outcome == "applied"
        w.refresh_from_db()
        assert w.balance_micros == -2_000_000

    def test_withdraw_refuses_promo_money(self):
        """Promo credit is not withdrawable: availability is balance minus
        active promo remainders."""
        t = _tenant()
        c = _customer(t)
        _wallet(c, balance=10_000_000)          # base 10
        _mint(t, c, kind="promo", amount=5_000_000)  # balance 15, promo 5
        refused = wallet_ops.withdraw(customer_id=c.id, tenant=t,
                                      amount_micros=12_000_000,
                                      idempotency_key=str(uuid.uuid4()))
        assert refused.outcome == "refused"
        assert refused.refusal_code == wallet_ops.INSUFFICIENT_WITHDRAWABLE
        assert refused.balance_micros == 15_000_000
        ok = wallet_ops.withdraw(customer_id=c.id, tenant=t,
                                 amount_micros=10_000_000,
                                 idempotency_key=str(uuid.uuid4()))
        assert ok.outcome == "applied"
        assert ok.balance_micros == 5_000_000
        # The withdrawal consumed no promo lot (exclude_promo).
        assert not GrantAllocation.objects.filter(
            allocation_type="withdrawal").exists()

    def test_refund_refuses_unknown_usage_event(self):
        t = _tenant()
        c = _customer(t)
        _wallet(c, balance=1_000_000)
        with patch("apps.metering.queries.get_usage_event_cost",
                   return_value=None):
            result = wallet_ops.refund_usage(
                customer_id=c.id, tenant=t, usage_event_id=uuid.uuid4(),
                idempotency_key=str(uuid.uuid4()))
        assert result.outcome == "refused"
        assert result.refusal_code == wallet_ops.USAGE_EVENT_NOT_FOUND

    def test_void_refuses_unknown_grant(self):
        t = _tenant()
        c = _customer(t)
        _wallet(c)
        result = wallet_ops.void_grant(customer_id=c.id, tenant=t,
                                       grant_id=uuid.uuid4())
        assert result.outcome == "refused"
        assert result.refusal_code == wallet_ops.GRANT_NOT_FOUND

    def test_mint_refuses_a_key_owned_by_a_non_grant_row(self):
        t = _tenant()
        c = _customer(t)
        _wallet(c, balance=1_000_000)
        key = str(uuid.uuid4())
        # Occupy grant:{key} with a non-GRANT row: a debit keyed that way.
        wallet_ops.debit(customer_id=c.id, tenant=t, amount_micros=1_000_000,
                         idempotency_key=f"grant:{key}")
        result = wallet_ops.mint_grant(
            customer_id=c.id, tenant=t, kind="promo", amount_micros=1_000_000,
            expires_at=None, idempotency_key=key)
        assert result.outcome == "refused"
        assert result.refusal_code == wallet_ops.IDEMPOTENCY_CONFLICT

    def test_a_refusal_still_commits_the_lazy_expiry(self):
        """THE semantic reason ops return refusals instead of raising: the
        expiry side effects a refused op triggered must land (the refusal
        quotes the post-expiry balance)."""
        t = _tenant()
        c = _customer(t)
        _wallet(c, balance=0)
        grant = _mint(t, c, kind="promo", amount=5_000_000,
                      expires_at=timezone.now() + timedelta(days=1))
        CreditGrant.objects.filter(pk=grant.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1))
        result = wallet_ops.withdraw(customer_id=c.id, tenant=t,
                                     amount_micros=1_000_000,
                                     idempotency_key=str(uuid.uuid4()))
        assert result.outcome == "refused"
        assert result.balance_micros == 0  # the promo lot expired away
        grant.refresh_from_db()
        assert grant.status == "expired"  # ...and that expiry COMMITTED
        assert _txns(Wallet.objects.get(customer=c), "GRANT_EXPIRY").exists()


# ---------------------------------------------------------------------------
# Replay quirks — preserved at the seam
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestReplays:
    def test_debit_credit_withdraw_replay_once(self):
        t = _tenant()
        c = _customer(t)
        w = _wallet(c, balance=20_000_000)
        for op, kwargs in (
            (wallet_ops.debit, {"amount_micros": 1_000_000}),
            (wallet_ops.credit, {"amount_micros": 1_000_000}),
            (wallet_ops.withdraw, {"amount_micros": 1_000_000}),
        ):
            key = str(uuid.uuid4())
            first = op(customer_id=c.id, tenant=t, idempotency_key=key, **kwargs)
            again = op(customer_id=c.id, tenant=t, idempotency_key=key, **kwargs)
            assert first.outcome == "applied"
            assert again.outcome == "replayed"
            assert again.transaction_id == first.transaction_id
            assert again.balance_micros == first.balance_micros
        w.refresh_from_db()
        assert w.balance_micros == 19_000_000
        assert _txns(w).count() == 3

    def test_refund_replay_answers_with_the_original_reference(self):
        """The refund replay quirk: refund_id on a replay is the stored row's
        reference_id (the usage event id), not the txn id."""
        t = _tenant()
        c = _customer(t)
        _wallet(c, balance=0)
        event_id = uuid.uuid4()
        key = str(uuid.uuid4())
        with patch("apps.metering.queries.get_usage_event_cost",
                   return_value=2_000_000):
            first = wallet_ops.refund_usage(
                customer_id=c.id, tenant=t, usage_event_id=event_id,
                idempotency_key=key)
            again = wallet_ops.refund_usage(
                customer_id=c.id, tenant=t, usage_event_id=event_id,
                idempotency_key=key)
        assert first.outcome == "applied"
        assert again.outcome == "replayed"
        assert again.reference_id == str(event_id)
        # Exactly one RefundRequested (winning branch only).
        assert OutboxEvent.objects.filter(
            event_type="refund.requested").count() == 1

    def test_void_replay_returns_the_lot_with_no_txn(self):
        t = _tenant()
        c = _customer(t)
        _wallet(c)
        grant = _mint(t, c, kind="promo", amount=3_000_000)
        first = wallet_ops.void_grant(customer_id=c.id, tenant=t,
                                      grant_id=grant.id)
        again = wallet_ops.void_grant(customer_id=c.id, tenant=t,
                                      grant_id=grant.id)
        assert first.outcome == "applied"
        assert again.outcome in ("replayed", "noop")
        assert again.transaction_id is None
        assert again.grant.status == "voided"
        assert _txns(Wallet.objects.get(customer=c), "GRANT_VOID").count() == 1

    def test_mint_replay_returns_the_original_grant_and_txn(self):
        t = _tenant()
        c = _customer(t)
        w = _wallet(c)
        key = str(uuid.uuid4())
        first = wallet_ops.mint_grant(
            customer_id=c.id, tenant=t, kind="paid", amount_micros=2_000_000,
            expires_at=None, idempotency_key=key)
        again = wallet_ops.mint_grant(
            customer_id=c.id, tenant=t, kind="paid", amount_micros=2_000_000,
            expires_at=None, idempotency_key=key)
        assert again.outcome == "replayed"
        assert again.grant.id == first.grant.id
        assert again.transaction_id == first.transaction_id
        w.refresh_from_db()
        assert w.balance_micros == 2_000_000  # minted once

    def test_drawdown_replay_logs_an_amount_mismatch(self, caplog):
        t = _tenant()
        c = _customer(t)
        w = _wallet(c, balance=10_000_000)
        event_id = str(uuid.uuid4())
        wallet_ops.draw_down_usage(customer_id=c.id, tenant=t,
                                   usage_event_id=event_id,
                                   billed_cost_micros=1_000_000)
        with caplog.at_level("ERROR", logger="ubb.billing"):
            again = wallet_ops.draw_down_usage(
                customer_id=c.id, tenant=t, usage_event_id=event_id,
                billed_cost_micros=2_000_000)
        assert again.outcome == "replayed"
        assert any("usage_deduction_amount_mismatch" in r.message
                   for r in caplog.records)
        w.refresh_from_db()
        assert w.balance_micros == 9_000_000  # debited once, first amount

    def test_top_up_replay_credits_once(self):
        t = _tenant()
        c = _customer(t)
        w = _wallet(c)
        key = f"auto_topup:pi_{uuid.uuid4()}"
        first = wallet_ops.credit_top_up(
            customer_id=c.id, tenant=t, amount_micros=5_000_000,
            idempotency_key=key, source="auto_topup", source_reference="a1",
            description="Auto top-up")
        again = wallet_ops.credit_top_up(
            customer_id=c.id, tenant=t, amount_micros=5_000_000,
            idempotency_key=key, source="auto_topup", source_reference="a1",
            description="Auto top-up")
        assert first.outcome == "applied"
        assert again.outcome == "replayed"
        w.refresh_from_db()
        assert w.balance_micros == 5_000_000
        assert CreditGrant.objects.filter(wallet=w, kind="paid").count() == 1


# ---------------------------------------------------------------------------
# Per-op expiry placement — parity-preserved (execution guardrail)
# ---------------------------------------------------------------------------


def _due_grant(t, c, amount=5_000_000):
    grant = _mint(t, c, kind="promo", amount=amount,
                  expires_at=timezone.now() + timedelta(days=1))
    CreditGrant.objects.filter(pk=grant.pk).update(
        expires_at=timezone.now() - timedelta(seconds=1))
    return grant


@pytest.mark.django_db
class TestExpiryPlacement:
    @pytest.mark.parametrize("op_name", [
        "debit", "withdraw", "refund_usage", "draw_down_usage",
        "claw_back_dispute", "claw_back_stripe_refund",
    ])
    def test_consuming_ops_expire_due_lots_first(self, op_name):
        t = _tenant()
        c = _customer(t)
        _wallet(c, balance=10_000_000)
        grant = _due_grant(t, c)  # balance 15, 5 of it due
        kwargs = {"customer_id": c.id, "tenant": t,
                  "idempotency_key": str(uuid.uuid4())}
        if op_name == "debit":
            wallet_ops.debit(amount_micros=1_000_000, **kwargs)
        elif op_name == "withdraw":
            wallet_ops.withdraw(amount_micros=1_000_000, **kwargs)
        elif op_name == "refund_usage":
            with patch("apps.metering.queries.get_usage_event_cost",
                       return_value=1_000_000):
                wallet_ops.refund_usage(usage_event_id=uuid.uuid4(), **kwargs)
        elif op_name == "draw_down_usage":
            wallet_ops.draw_down_usage(
                customer_id=c.id, tenant=t, usage_event_id=str(uuid.uuid4()),
                billed_cost_micros=1_000_000)
        elif op_name == "claw_back_dispute":
            wallet_ops.claw_back_dispute(
                customer_id=c.id, tenant=t, amount_micros=1_000_000,
                dispute_id="dp_1", charge_id="ch_1", attempt_id=uuid.uuid4())
        else:
            wallet_ops.claw_back_stripe_refund(
                customer_id=c.id, tenant=t, amount_micros=1_000_000,
                refund_id="re_1", attempt_id=uuid.uuid4())
        grant.refresh_from_db()
        assert grant.status == "expired", op_name
        assert grant.remaining_micros == 0

    @pytest.mark.parametrize("op_name", ["credit", "mint_grant", "credit_top_up"])
    def test_pure_credit_ops_do_not_expire(self, op_name):
        """credit / mint / top-up never ran lazy expiry — kept that way."""
        t = _tenant()
        c = _customer(t)
        _wallet(c, balance=10_000_000)
        grant = _due_grant(t, c)
        kwargs = {"customer_id": c.id, "tenant": t,
                  "idempotency_key": str(uuid.uuid4())}
        if op_name == "credit":
            wallet_ops.credit(amount_micros=1_000_000, **kwargs)
        elif op_name == "mint_grant":
            wallet_ops.mint_grant(kind="paid", amount_micros=1_000_000,
                                  expires_at=None, **kwargs)
        else:
            wallet_ops.credit_top_up(
                amount_micros=1_000_000, source="checkout",
                source_reference="s1", description="Stripe top-up", **kwargs)
        grant.refresh_from_db()
        assert grant.status == "active", op_name  # the due lot survived

    def test_void_expires_first_then_noops_on_the_expired_lot(self):
        t = _tenant()
        c = _customer(t)
        _wallet(c, balance=0)
        grant = _due_grant(t, c)
        result = wallet_ops.void_grant(customer_id=c.id, tenant=t,
                                       grant_id=grant.id)
        assert result.outcome == "noop"
        assert result.grant.status == "expired"  # expiry won; the void no-oped
        assert not _txns(Wallet.objects.get(customer=c), "GRANT_VOID").exists()


# ---------------------------------------------------------------------------
# Money rules in the middle: void clamp, clawback cascade, audit stamp
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestMoneyRules:
    def test_void_clamps_to_the_spendable_balance(self):
        """Voiding never drives the balance negative (G3-style clamp)."""
        t = _tenant()
        c = _customer(t)
        _wallet(c, balance=0)
        grant = _mint(t, c, kind="promo", amount=10_000_000)  # balance 10
        wallet_ops.draw_down_usage(customer_id=c.id, tenant=t,
                                   usage_event_id=str(uuid.uuid4()),
                                   billed_cost_micros=7_000_000)  # balance 3
        result = wallet_ops.void_grant(customer_id=c.id, tenant=t,
                                       grant_id=grant.id)
        assert result.outcome == "applied"
        assert result.amount_micros == -3_000_000  # clamped: min(remaining=3, balance=3)
        assert result.balance_micros == 0
        grant = result.grant
        assert grant.status == "voided"
        assert grant.remaining_micros == 0

    def test_clawback_voids_the_source_lot_then_cascades(self):
        """Dispute clawback: the reversed top-up's own lot is voided first
        (same bucket the void endpoint uses); other lots are consumed only as
        far as G1 demands."""
        t = _tenant()
        c = _customer(t)
        w = _wallet(c, balance=0)
        attempt_id = uuid.uuid4()
        wallet_ops.credit_top_up(
            customer_id=c.id, tenant=t, amount_micros=10_000_000,
            idempotency_key=f"topup:cs_{uuid.uuid4()}", source="checkout",
            source_reference=str(attempt_id), description="Stripe top-up")
        api_lot = _mint(t, c, kind="promo", amount=5_000_000)  # balance 15
        result = wallet_ops.claw_back_dispute(
            customer_id=c.id, tenant=t, amount_micros=10_000_000,
            dispute_id="dp_1", charge_id="ch_1", attempt_id=attempt_id)
        assert result.outcome == "applied"
        assert result.balance_micros == 5_000_000
        source = CreditGrant.objects.get(wallet=w, source="checkout")
        assert source.status == "voided"
        assert source.voided_micros == 10_000_000
        api_lot.refresh_from_db()
        assert api_lot.status == "active"
        assert api_lot.remaining_micros == 5_000_000  # G1 already holds

    def test_clawback_never_voids_a_non_topup_lot_as_source(self):
        """Only top-up-born lots qualify as the clawback source — an API lot
        sharing the reference is consumed by the cascade, never voided."""
        t = _tenant()
        c = _customer(t)
        w = _wallet(c, balance=0)
        attempt_id = uuid.uuid4()
        # An API grant that (pathologically) shares the attempt reference.
        result = wallet_ops.mint_grant(
            customer_id=c.id, tenant=t, kind="promo", amount_micros=8_000_000,
            expires_at=None, idempotency_key=str(attempt_id))
        api_lot = result.grant
        claw = wallet_ops.claw_back_stripe_refund(
            customer_id=c.id, tenant=t, amount_micros=3_000_000,
            refund_id="re_1", attempt_id=attempt_id)
        assert claw.outcome == "applied"
        api_lot.refresh_from_db()
        assert api_lot.voided_micros == 0          # not treated as the source
        assert api_lot.remaining_micros == 5_000_000  # cascade-consumed to G1
        assert GrantAllocation.objects.filter(
            grant=api_lot, allocation_type="clawback").exists()

    def test_audit_value_is_stamped_on_the_ledger_row(self):
        t = _tenant()
        c = _customer(t)
        _wallet(c, balance=5_000_000)
        result = wallet_ops.debit(
            customer_id=c.id, tenant=t, amount_micros=1_000_000,
            idempotency_key=str(uuid.uuid4()),
            audit=wallet_ops.Audit(actor="ops@t.co", reason_code="correction",
                                   reference="ref-1"))
        txn = WalletTransaction.objects.get(pk=result.transaction_id)
        assert txn.actor == "ops@t.co"
        assert txn.reason_code == "correction"
        assert txn.reference_id == "ref-1"
        assert txn.description == "External debit"

    def test_top_up_lot_expiry_comes_from_the_billing_profile(self):
        t = _tenant()
        c = _customer(t)
        w = _wallet(c)
        CustomerBillingProfile.objects.create(customer=c,
                                              topup_grant_expiry_days=30)
        wallet_ops.credit_top_up(
            customer_id=c.id, tenant=t, amount_micros=2_000_000,
            idempotency_key=f"topup:cs_{uuid.uuid4()}", source="checkout",
            source_reference="a1", description="Stripe top-up")
        lot = CreditGrant.objects.get(wallet=w)
        assert lot.kind == "paid"
        assert lot.expires_at is not None
        assert lot.expires_at > timezone.now() + timedelta(days=29)

    def test_refund_re_funds_the_funding_lot(self):
        """A promo-funded charge refunds as promo, never as cash."""
        t = _tenant()
        c = _customer(t)
        w = _wallet(c, balance=0)
        lot = _mint(t, c, kind="promo", amount=5_000_000)
        event_id = uuid.uuid4()
        wallet_ops.draw_down_usage(customer_id=c.id, tenant=t,
                                   usage_event_id=event_id,
                                   billed_cost_micros=4_000_000)
        with patch("apps.metering.queries.get_usage_event_cost",
                   return_value=4_000_000):
            result = wallet_ops.refund_usage(
                customer_id=c.id, tenant=t, usage_event_id=event_id,
                idempotency_key=str(uuid.uuid4()))
        assert result.outcome == "applied"
        lot.refresh_from_db()
        assert lot.remaining_micros == 5_000_000  # restored into the lot
        w.refresh_from_db()
        assert w.balance_micros == 5_000_000


# ---------------------------------------------------------------------------
# The drawdown tail — winning branch only; the repair flag suppresses it (I12)
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestDrawdownTail:
    def test_zero_cross_emits_overage_and_tier1_suspension(self):
        t = _tenant()  # enforcement off -> Tier-1 baseline suspension
        c = _customer(t)
        _wallet(c, balance=1_000_000)
        result = wallet_ops.draw_down_usage(
            customer_id=c.id, tenant=t, usage_event_id=str(uuid.uuid4()),
            billed_cost_micros=2_000_000)
        assert result.outcome == "applied"
        assert OutboxEvent.objects.filter(
            event_type="billing.balance_overage").count() == 1
        assert OutboxEvent.objects.filter(
            event_type="billing.customer_suspended").count() == 1
        c.refresh_from_db()
        assert c.status == "suspended"
        assert c.suspension_reason == "min_balance_exceeded"

    def test_balance_low_fires_under_the_topup_trigger(self):
        t = _tenant()
        c = _customer(t)
        _wallet(c, balance=10_000_000)
        AutoTopUpConfig.objects.create(
            customer=c, is_enabled=True, trigger_threshold_micros=8_000_000,
            top_up_amount_micros=20_000_000)
        wallet_ops.draw_down_usage(customer_id=c.id, tenant=t,
                                   usage_event_id=str(uuid.uuid4()),
                                   billed_cost_micros=3_000_000)
        assert OutboxEvent.objects.filter(
            event_type="billing.balance_low").count() == 1

    def test_enforcing_floor_cross_drives_the_stop_lane(self):
        t = _tenant(enforcement_mode="enforcing")
        c = _customer(t)
        _wallet(c, balance=1_000_000)
        with patch("apps.billing.gating.services.stop_signal_service."
                   "StopSignalService.drive_stop") as drive, \
             patch("apps.billing.gating.services.live_ledger_service."
                   "LiveLedgerService.ensure_stop_flag") as flag:
            wallet_ops.draw_down_usage(
                customer_id=c.id, tenant=t, usage_event_id=str(uuid.uuid4()),
                billed_cost_micros=2_000_000)
        assert drive.called
        assert flag.called
        # Enforcing: the folded suspension rides the signal ledger, never the
        # Tier-1 direct write.
        assert not OutboxEvent.objects.filter(
            event_type="billing.customer_suspended").exists()

    def test_repair_flag_suppresses_the_whole_tail(self):
        """I12: a back-correction debits and allocates but never re-fires
        signals, suspensions, or top-up nudges."""
        t = _tenant()
        c = _customer(t)
        w = _wallet(c, balance=1_000_000)
        AutoTopUpConfig.objects.create(
            customer=c, is_enabled=True, trigger_threshold_micros=8_000_000,
            top_up_amount_micros=20_000_000)
        result = wallet_ops.draw_down_usage(
            customer_id=c.id, tenant=t, usage_event_id=str(uuid.uuid4()),
            billed_cost_micros=2_000_000, repair=True)
        assert result.outcome == "applied"
        w.refresh_from_db()
        assert w.balance_micros == -1_000_000
        assert not OutboxEvent.objects.exclude(
            event_type="billing.credit_grant_expired").exists()
        c.refresh_from_db()
        assert c.status == "active"
        txn = WalletTransaction.objects.get(pk=result.transaction_id)
        assert txn.description.startswith("Usage (reconciled): ")

    def test_withdraw_event_winning_branch_only(self):
        t = _tenant()
        c = _customer(t)
        _wallet(c, balance=5_000_000)
        key = str(uuid.uuid4())
        wallet_ops.withdraw(customer_id=c.id, tenant=t,
                            amount_micros=1_000_000, idempotency_key=key)
        wallet_ops.withdraw(customer_id=c.id, tenant=t,
                            amount_micros=1_000_000, idempotency_key=key)
        wallet_ops.withdraw(customer_id=c.id, tenant=t,
                            amount_micros=99_000_000,
                            idempotency_key=str(uuid.uuid4()))  # refused
        assert OutboxEvent.objects.filter(
            event_type="billing.withdrawal_requested").count() == 1


# ---------------------------------------------------------------------------
# The sweep wrapper
# ---------------------------------------------------------------------------


@pytest.mark.django_db
class TestExpireDueSweep:
    def test_sweep_expires_and_counts(self):
        t = _tenant()
        c = _customer(t)
        w = _wallet(c, balance=0)
        _due_grant(t, c, amount=3_000_000)
        assert wallet_ops.expire_due_sweep(c.id) == 1
        assert wallet_ops.expire_due_sweep(c.id) == 0  # nothing left due
        w.refresh_from_db()
        assert w.balance_micros == 0
        assert _txns(w, "GRANT_EXPIRY").count() == 1
