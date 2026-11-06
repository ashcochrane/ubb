"""Pin 8 (#42, spec §G/§L): enforcement mode is two-position.

The choices are two-position on every surface — `advisory` is retired, and the
config route refuses it; `off` creates none of the enforcing-only stop/control
artefacts — no counters, no `StopSignalState`, no Redis flag, no
`customer.stopped`/`customer.stop_cleared`, no tagging — while the Tier-1
baseline (drawdown, zero-crossing early warning, level-based suspend) is
untouched. NOT "byte-for-byte pre-enforcement" (R10 Stage C2, ruled
2026-11-03, §7 item 25): the level-based suspension is lifted from the
DURABLE wallet balance under `off` too — the credit hook and the hourly pass,
through the one reactivation site — and that real `suspended -> active`
transition emits `customer.reactivated`, under `off` as under `enforcing`,
where the existing stop/control semantics and artefacts stay unchanged and
that event is the only additive behaviour. The pins that once said
"byte-for-byte" pinned BILLING BLOCKER F-1: a floor suspension no credit
could ever clear.

Before the cutover (#190) this module also drove `tenants/0019`'s data step,
which moved every stored `advisory` row to `off`; that step left with the
squashed chain, and what it left behind — the two-position choice set — is
pinned below.
"""
import contextlib
import json
import uuid
from dataclasses import asdict
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.db import transaction
from django.test import Client

from apps.billing.gating.models import CustomerSpendPool, StopSignalState
from apps.billing.gating.patrol import OUTCOME_REPAIRED
from apps.billing.gating.repair import repair_live_balances
from apps.billing.gating.services.live_counter import Door, LiveCounter
from apps.billing.gating.services.risk_service import RiskService
from apps.billing.gating.tasks import _per_owner_reconcile, reconcile_live_ledgers
from apps.billing.handlers import handle_usage_recorded_billing
from apps.billing.locking import lock_for_billing
from apps.billing.tenant_billing.models import TenantBillingPeriod
from apps.billing.wallets import operations as wallet_ops
from apps.billing.wallets.models import (
    CustomerBillingProfile, Wallet, WalletReservation, WalletTransaction)
from apps.metering.pricing.tests._helpers import (
    a_rule_that_prices_what_it_measures, priced_at)
from apps.metering.usage.models import Posting
from apps.metering.usage.tests._helpers import a_posting
from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.platform.events.schemas import (
    CustomerReactivated, CustomerStopCleared, CustomerStopped, UsageRecorded,
    WalletPolicySoftFloorCleared, WalletPolicySoftFloorCrossed)
from apps.platform.tenants.flags import holds_a_wallet
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.work import reasons
from apps.platform.tenants.tests._rails import activate_the_rail
from core.exceptions import NoWalletSubjectError
from core.vocabulary import (
    AFFORDABILITY_REASON_CUSTOMER_SPEND_POOL_EXCEEDED, GRANT_KIND_PROMO,
    GRANT_SOURCE_CHECKOUT)

#: The billing modes that hold no wallet (`holds_a_wallet` is false). Both
#: may carry the `billing` product; neither has a wallet subject.
NO_WALLET_MODES = ("external", "postpaid")


def _tenant(mode="prepaid", enf="off"):
    return Tenant.objects.create(name="T", products=["metering", "billing"],
                                 billing_mode=mode, enforcement_mode=enf)


@pytest.mark.usefixtures("rail_activated")
@pytest.mark.django_db
class TestAdvisoryRetired:
    def test_choices_are_two_position(self):
        from apps.platform.tenants.models import ENFORCEMENT_MODE_CHOICES
        assert [c[0] for c in ENFORCEMENT_MODE_CHOICES] == ["off", "enforcing"]

    def test_patch_advisory_refused_422(self):
        t = _tenant(enf="off")
        _k, raw = TenantApiKey.create_key(t, label="t")
        resp = Client().patch("/api/v1/tenant/config",
                              data=json.dumps({"enforcement_mode": "advisory"}),
                              content_type="application/json",
                              HTTP_AUTHORIZATION=f"Bearer {raw}")
        assert resp.status_code == 422
        t.refresh_from_db()
        assert t.enforcement_mode == "off"  # unchanged


@pytest.mark.django_db
class TestOffCreatesNoEnforcementArtefacts:
    def setup_method(self):
        # A money-mode tenant needs the payment rail activated first (G27);
        # asked for here, by name, before the tenant is built.
        activate_the_rail()
        cache.clear()

    def test_floor_crossing_leaves_no_enforcement_trace(self):
        # A crossing that would fire the whole suite in enforcing leaves
        # NOTHING in off: no live counter, no stop flag, no signal ledger
        # row, no stop/soft-floor events, no stop-context tag — while the
        # event itself lands and bills (Tier-1 kept).
        client = Client()
        t = _tenant(enf="off")
        _k, raw = TenantApiKey.create_key(t, label="t")
        c = Customer.objects.create(tenant=t, external_id="jim")
        Wallet.objects.create(customer=c, balance_micros=5_000_000)
        # 8,000,000 is what the tenant's rule charges for this event now (#365).
        a_rule_that_prices_what_it_measures(t)
        r = client.post("/api/v1/metering/usage", data=json.dumps({
            "customer_id": str(c.id), "idempotency_key": "k1",
            "measurements": priced_at(8_000_000)}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {raw}")
        assert r.status_code == 200
        body = r.json()
        assert body["stop"] is False and body["stop_reason"] is None
        ev = Posting.objects.get(tenant=t, idempotency_key="k1")
        assert ev.stop_context is None                            # no tagging
        assert Door.balance(c.id) is None                         # no counter
        assert Door.stop_reason(c.id) is None                     # no flag
        assert not StopSignalState.objects.filter(owner=c).exists()  # no ledger
        assert not OutboxEvent.objects.filter(event_type__in=[
            CustomerStopped.EVENT_TYPE, CustomerStopCleared.EVENT_TYPE,
            WalletPolicySoftFloorCrossed.EVENT_TYPE,
            WalletPolicySoftFloorCleared.EVENT_TYPE]).exists()  # no signals

    def test_tier1_baseline_survives_untouched(self):
        # The pre-enforcement reactions still run in off: durable drawdown,
        # the zero-crossing early warning, and the level-based baseline
        # suspend — none of them are enforcement-mode gated.
        t = _tenant(enf="off")
        c = Customer.objects.create(tenant=t, external_id="jim")
        Wallet.objects.create(customer=c, balance_micros=5_000_000)
        handle_usage_recorded_billing(str(uuid.uuid4()), asdict(UsageRecorded(
            pricing_status_reason=None,
            tenant_id=t.id, customer_id=c.id,
            event_id=str(uuid.uuid4()), cost_micros=8_000_000)))
        w = Wallet.objects.get(customer=c)
        assert w.balance_micros == -3_000_000                     # billed
        c.refresh_from_db()
        assert c.status == "suspended"                            # baseline
        assert c.suspension_reason == reasons.HARD_FLOOR
        assert OutboxEvent.objects.filter(
            event_type="wallet.balance_overage").count() == 1    # early warning
        assert OutboxEvent.objects.filter(
            event_type="customer.suspended").count() == 1
        assert not OutboxEvent.objects.filter(event_type=CustomerStopped.EVENT_TYPE).exists()
        assert not StopSignalState.objects.filter(owner=c).exists()


@contextlib.contextmanager
def _committing(capture):
    """Run a block as it commits in life: the on-commit callbacks fire (the
    credit hook, the outbox dispatch) with the Celery hand-off patched away."""
    with patch("apps.platform.events.tasks.process_single_event"):
        with capture(execute=True):
            yield


def _reactivated(c):
    return OutboxEvent.objects.filter(event_type=CustomerReactivated.EVENT_TYPE,
                                      payload__customer_id=str(c.id))


def _stop_pair(c):
    return OutboxEvent.objects.filter(
        event_type__in=[CustomerStopped.EVENT_TYPE, CustomerStopCleared.EVENT_TYPE],
        payload__owner_id=str(c.id))


@pytest.mark.django_db
class TestOffRecoversAMoneySuspensionFromDurableTruth:
    """R10 Stage C2, F-1 (BILLING BLOCKER): under `off`, on a prepaid tenant, a
    customer the silent level test suspended on the wallet's hard floor is
    reactivated from the DURABLE wallet balance — after any positive durable
    wallet move (the credit hook) and on the hourly pass — through the one
    reactivation site and nothing else: no live counter, no stop flag, no
    `StopSignalState`, no `customer.stopped`/`customer.stop_cleared`. The real
    `suspended -> active` transition emits `customer.reactivated` exactly
    once, under `off` as under `enforcing` (RULED Q3; §7 item 25).

    Before C2 every one of these clearing acts left the customer suspended
    for good (`R10-BILLING-READINESS/evidence/04-prepaid-off.txt` step 9).
    """

    def setup_method(self):
        activate_the_rail()
        cache.clear()

    def _suspended_on_the_floor(self, enf="off", balance=5_000_000, usage=8_000_000):
        t = _tenant(enf=enf)
        c = Customer.objects.create(tenant=t, external_id="jim")
        Wallet.objects.create(customer=c, balance_micros=balance)
        posting = a_posting(tenant=t, customer=c, idempotency_key="u1",
                            provider_cost_micros=usage, billed_cost_micros=usage)
        handle_usage_recorded_billing(str(uuid.uuid4()), asdict(UsageRecorded(
            pricing_status_reason=None, tenant_id=t.id, customer_id=c.id,
            event_id=str(posting.id), cost_micros=usage)))
        c.refresh_from_db()
        assert (c.status, c.suspension_reason) == ("suspended", reasons.HARD_FLOOR)
        return t, c, posting

    def _no_enforcement_artefacts(self, c):
        assert Door.balance(c.id) is None                         # no counter
        assert Door.stop_reason(c.id) is None                     # no flag
        assert not StopSignalState.objects.filter(owner=c).exists()  # no ledger
        assert not _stop_pair(c).exists()                         # no signals

    def _is_active_again(self, c, *, balance_micros):
        c.refresh_from_db()
        assert (c.status, c.suspension_reason) == ("active", "")
        assert _reactivated(c).count() == 1
        payload = _reactivated(c).get().payload
        assert payload["tenant_id"] == str(c.tenant_id)
        assert payload["customer_id"] == str(c.id)
        assert payload["reason_code"] == reasons.HARD_FLOOR     # the reason LEFT
        assert payload["balance_micros"] == balance_micros
        self._no_enforcement_artefacts(c)

    def test_a_credit_lifts_the_floor_suspension(self, django_capture_on_commit_callbacks):
        t, c, _ = self._suspended_on_the_floor()                 # balance -3M
        with _committing(django_capture_on_commit_callbacks):
            wallet_ops.credit(customer_id=c.id, tenant=t, amount_micros=10_000_000,
                              idempotency_key="cr1")
        self._is_active_again(c, balance_micros=7_000_000)

    def test_a_grant_lifts_it(self, django_capture_on_commit_callbacks):
        t, c, _ = self._suspended_on_the_floor()
        with _committing(django_capture_on_commit_callbacks):
            wallet_ops.mint_grant(customer_id=c.id, tenant=t, kind=GRANT_KIND_PROMO,
                                  amount_micros=4_000_000, expires_at=None,
                                  idempotency_key="g1")
        self._is_active_again(c, balance_micros=1_000_000)

    def test_a_top_up_lifts_it(self, django_capture_on_commit_callbacks):
        t, c, _ = self._suspended_on_the_floor()
        with _committing(django_capture_on_commit_callbacks):
            wallet_ops.credit_top_up(customer_id=c.id, tenant=t, amount_micros=3_000_000,
                                     idempotency_key="topup:cs_1",
                                     source=GRANT_SOURCE_CHECKOUT,
                                     source_reference="cs_1", description="Stripe top-up")
        self._is_active_again(c, balance_micros=0)              # AT the floor is recovered

    def test_a_refund_lifts_it(self, django_capture_on_commit_callbacks):
        t, c, posting = self._suspended_on_the_floor()
        with _committing(django_capture_on_commit_callbacks):
            wallet_ops.refund_usage(customer_id=c.id, tenant=t, usage_event_id=posting.id,
                                    idempotency_key="rf1")
        self._is_active_again(c, balance_micros=5_000_000)

    def test_the_hourly_pass_lifts_it(self):
        # The credit hook was lost (a crashed worker between commit and hook):
        # only the durable wallet shows the recovery. The hourly pass visits
        # the floor-suspended owners of an `off` tenant for this check alone.
        t, c, _ = self._suspended_on_the_floor()
        Wallet.objects.filter(customer=c).update(balance_micros=2_000_000)
        reconcile_live_ledgers()
        self._is_active_again(c, balance_micros=2_000_000)
        reconcile_live_ledgers()                                  # idempotent
        assert _reactivated(c).count() == 1

    def test_a_credit_that_stays_below_the_floor_leaves_it(self, django_capture_on_commit_callbacks):
        t, c, _ = self._suspended_on_the_floor()                 # -3M
        with _committing(django_capture_on_commit_callbacks):
            wallet_ops.credit(customer_id=c.id, tenant=t, amount_micros=1_000_000,
                              idempotency_key="cr1")             # -2M, still past 0
        c.refresh_from_db()
        assert (c.status, c.suspension_reason) == ("suspended", reasons.HARD_FLOOR)
        assert not _reactivated(c).exists()
        self._no_enforcement_artefacts(c)

    def test_a_manual_hold_is_never_lifted(self, django_capture_on_commit_callbacks):
        # A manual hold is `suspended` with an EMPTY reason (R10 Stage C4, PLAN
        # §7 item 41); only its own release lifts it, never a credit.
        t, c, _ = self._suspended_on_the_floor()
        Customer.objects.filter(id=c.id).update(suspension_reason="")
        with _committing(django_capture_on_commit_callbacks):
            wallet_ops.credit(customer_id=c.id, tenant=t, amount_micros=10_000_000,
                              idempotency_key="cr1")
        c.refresh_from_db()
        assert (c.status, c.suspension_reason) == ("suspended", "")
        assert not _reactivated(c).exists()

    def test_a_credit_never_lifts_a_pool_suspension_under_off(self, django_capture_on_commit_callbacks):
        # A balance says nothing about spend: a pool suspension left behind
        # (here, by a switch from enforcing) is not the durable balance's to
        # lift, however healthy the wallet. Only the balance suspensions are.
        t = _tenant(enf="off")
        c = Customer.objects.create(tenant=t, external_id="jim", status="suspended",
                                    suspension_reason=reasons.CUSTOMER_SPEND_POOL)
        Wallet.objects.create(customer=c, balance_micros=5_000_000)
        with _committing(django_capture_on_commit_callbacks):
            wallet_ops.credit(customer_id=c.id, tenant=t, amount_micros=10_000_000,
                              idempotency_key="cr1")
        reconcile_live_ledgers()
        c.refresh_from_db()
        assert (c.status, c.suspension_reason) == ("suspended", reasons.CUSTOMER_SPEND_POOL)
        assert not _reactivated(c).exists()
        self._no_enforcement_artefacts(c)

    def test_a_standing_payment_failure_holds_the_owner_and_takes_over_the_reason(
            self, django_capture_on_commit_callbacks):
        # RULED Q4's multi-invoice rule at the one reactivation site: the
        # floor recovered, but a local invoice of the owner still stands
        # failed — so the owner stays suspended, now for the cause that
        # stands, and the paid invoice is what brings it back.
        import datetime
        from types import SimpleNamespace as NS
        from django.utils import timezone
        from api.v1.webhooks import handle_invoice_paid
        from apps.billing.invoicing.models import CustomerUsageInvoice
        t, c, _ = self._suspended_on_the_floor()
        Tenant.objects.filter(id=t.id).update(stripe_connected_account_id="acct_c2")
        t.refresh_from_db()
        CustomerUsageInvoice.objects.create(
            tenant=t, customer=c, period_start=datetime.date(2026, 1, 1),
            period_end=datetime.date(2026, 2, 1), status="pushed",
            stripe_invoice_id="in_c2_held", payment_status="open",
            payment_failed_at=timezone.now())
        with _committing(django_capture_on_commit_callbacks):
            wallet_ops.credit(customer_id=c.id, tenant=t, amount_micros=10_000_000,
                              idempotency_key="cr1")
        c.refresh_from_db()
        assert (c.status, c.suspension_reason) == ("suspended", reasons.PAYMENT_FAILED)
        assert not _reactivated(c).exists()
        handle_invoice_paid(NS(account="acct_c2", livemode=True, data=NS(object=NS(
            id="in_c2_held", subscription=None, parent=None,
            hosted_invoice_url="", invoice_pdf=""))))
        c.refresh_from_db()
        assert (c.status, c.suspension_reason) == ("active", "")
        assert _reactivated(c).count() == 1
        assert _reactivated(c).get().payload["reason_code"] == reasons.PAYMENT_FAILED
        self._no_enforcement_artefacts(c)

    def test_the_off_pass_never_raises_and_every_tenant_is_still_visited(self, monkeypatch):
        # The hourly beat visits every tenant; a failure in one `off`
        # tenant's recovery pass must not cost the rest their patrol.
        from apps.billing.gating import patrol
        first = _tenant(enf="off")
        second = _tenant(enf="off")
        monkeypatch.setattr(LiveCounter, "BALANCE_SUSPEND_REASONS", object(), raising=False)
        visited = []
        monkeypatch.setattr(patrol, "run_patrol",
                            lambda tenant, **kw: visited.append(tenant.id))
        assert _per_owner_reconcile(first) == 0
        reconcile_live_ledgers()
        assert {first.id, second.id} <= set(visited)

    def test_customer_reactivated_fires_exactly_once(self, django_capture_on_commit_callbacks):
        t, c, _ = self._suspended_on_the_floor()
        with _committing(django_capture_on_commit_callbacks):
            wallet_ops.credit(customer_id=c.id, tenant=t, amount_micros=10_000_000,
                              idempotency_key="cr1")
        self._is_active_again(c, balance_micros=7_000_000)
        with _committing(django_capture_on_commit_callbacks):
            wallet_ops.credit(customer_id=c.id, tenant=t, amount_micros=1_000_000,
                              idempotency_key="cr2")             # already active
        reconcile_live_ledgers()                                  # the hourly pass finds it active
        assert _reactivated(c).count() == 1

    def test_no_event_when_the_status_does_not_change(self, django_capture_on_commit_callbacks):
        t = _tenant(enf="off")
        c = Customer.objects.create(tenant=t, external_id="jim")
        Wallet.objects.create(customer=c, balance_micros=5_000_000)
        with _committing(django_capture_on_commit_callbacks):
            wallet_ops.credit(customer_id=c.id, tenant=t, amount_micros=1_000_000,
                              idempotency_key="cr1")             # never suspended
        reconcile_live_ledgers()
        c.refresh_from_db()
        assert c.status == "active"
        assert not _reactivated(c).exists()

    def test_a_mode_flip_no_longer_strands_a_money_suspension(self, django_capture_on_commit_callbacks):
        # Suspended under ENFORCING (episode, flag, suspended), then the tenant
        # is switched off: before C2 nothing could ever clear it. The credit
        # now lifts it from durable truth — the stale enforcing artefacts are
        # the config route's cleanup to tidy (D17), not this lane's.
        t, c, _ = self._suspended_on_the_floor(enf="enforcing")
        assert StopSignalState.objects.filter(owner=c, state="stopped").exists()
        Tenant.objects.filter(id=t.id).update(enforcement_mode="off")
        t.refresh_from_db()
        with _committing(django_capture_on_commit_callbacks):
            wallet_ops.credit(customer_id=c.id, tenant=t, amount_micros=10_000_000,
                              idempotency_key="cr1")
        c.refresh_from_db()
        assert (c.status, c.suspension_reason) == ("active", "")
        assert _reactivated(c).count() == 1
        assert not OutboxEvent.objects.filter(
            event_type=CustomerStopCleared.EVENT_TYPE).exists()   # no control clear under off

    def test_the_reverse_flip_clears_too(self, django_capture_on_commit_callbacks):
        # Suspended under OFF, then enforcing switched on: the enforcing credit
        # hook finds no open line to clear (none was ever opened) and still
        # lifts the suspension from the durable balance — once, announced.
        t, c, _ = self._suspended_on_the_floor(enf="off")
        Tenant.objects.filter(id=t.id).update(enforcement_mode="enforcing")
        t.refresh_from_db()
        with _committing(django_capture_on_commit_callbacks):
            wallet_ops.credit(customer_id=c.id, tenant=t, amount_micros=10_000_000,
                              idempotency_key="cr1")
        c.refresh_from_db()
        assert (c.status, c.suspension_reason) == ("active", "")
        assert _reactivated(c).count() == 1
        assert not _stop_pair(c).exists()


@pytest.mark.django_db
class TestEnforcingEmitsReactivatedBesideStopCleared:
    """§7 item 25: under `enforcing` the stop/control artefacts are what they
    always were — the same episode opened and cleared, the same flag, the
    same `customer.stopped` / `customer.stop_cleared` — and the ONLY additive
    behaviour is `customer.reactivated`, exactly once, on the real
    `suspended -> active` transition beside the control clear."""

    def setup_method(self):
        activate_the_rail()
        cache.clear()

    def test_both_events_fire_each_once_on_a_recovery(self, django_capture_on_commit_callbacks):
        t = _tenant(enf="enforcing")
        c = Customer.objects.create(tenant=t, external_id="jim")
        Wallet.objects.create(customer=c, balance_micros=5_000_000)
        handle_usage_recorded_billing(str(uuid.uuid4()), asdict(UsageRecorded(
            pricing_status_reason=None, tenant_id=t.id, customer_id=c.id,
            event_id=str(uuid.uuid4()), cost_micros=8_000_000)))
        c.refresh_from_db()
        assert (c.status, c.suspension_reason) == ("suspended", reasons.HARD_FLOOR)
        episode = StopSignalState.objects.get(owner=c, state="stopped")
        assert Door.stop_reason(c.id) == reasons.HARD_FLOOR
        with _committing(django_capture_on_commit_callbacks):
            wallet_ops.credit(customer_id=c.id, tenant=t, amount_micros=10_000_000,
                              idempotency_key="cr1")
            wallet_ops.credit(customer_id=c.id, tenant=t, amount_micros=1_000_000,
                              idempotency_key="cr2")
        c.refresh_from_db()
        assert (c.status, c.suspension_reason) == ("active", "")
        episode.refresh_from_db()
        assert episode.state == "cleared"                         # the same artefacts, as before
        assert Door.stop_reason(c.id) is None
        cleared = OutboxEvent.objects.filter(event_type=CustomerStopCleared.EVENT_TYPE)
        assert cleared.count() == 1
        assert cleared.get().payload["episode_seq"] == episode.episode_seq
        assert _reactivated(c).count() == 1
        payload = _reactivated(c).get().payload
        assert payload["reason_code"] == reasons.HARD_FLOOR
        assert payload["balance_micros"] == 8_000_000

    def test_a_tenant_without_a_wallet_never_clears_dispute_lost_without_a_balance(self):
        # RULED Q4 b: `dispute_lost` clears ONLY by the durable balance rule.
        # Where no wallet is held there is no balance to recover, so the
        # enforcing resume's no-wallet branch clears the money pair as before
        # and never a lost dispute.
        from apps.billing.gating.services.stop_signal_service import CLEAR_RECONCILED
        t = _tenant(mode="postpaid", enf="enforcing")
        c = Customer.objects.create(tenant=t, external_id="jim", status="suspended",
                                    suspension_reason=reasons.DISPUTE_LOST)
        LiveCounter.resume(c.id, t, line=reasons.CUSTOMER_SPEND_POOL,
                           clear_reason=CLEAR_RECONCILED)
        c.refresh_from_db()
        assert (c.status, c.suspension_reason) == ("suspended", reasons.DISPUTE_LOST)
        assert not _reactivated(c).exists()


@pytest.mark.django_db
class TestExternalHasNoWalletPolicySubject:
    """W7 preparation finding F3, ruled 2026-10-30: wallet-floor enforcement has
    no subject for an `external` tenant, and an absent wallet is never a
    zero-balance wallet.

    Before the fix every wallet leg asked "not postpaid?", which an `external`
    tenant answered YES: under `enforcing` its first PRICED event seeded a live
    balance of 0 from the wallet it does not have, crossed a floor of 0, opened
    a `hard_floor` episode and suspended the customer — with no clear path,
    because the reconcile visits wallet holders. `enforcing` stays usable: what
    it governs for an external tenant is the pool and, always, the unit
    ceilings, which ask no wallet. No rail is needed — `external` is not a
    money mode.
    """

    def setup_method(self):
        cache.clear()

    def _external(self, *, products=("metering",)):
        return Tenant.objects.create(name="X", products=list(products),
                                     billing_mode="external",
                                     enforcement_mode="enforcing")

    def _recorded(self, client, raw, c, key, **fields):
        r = client.post("/api/v1/metering/usage", data=json.dumps({
            "customer_id": str(c.id), "idempotency_key": key, **fields}),
            content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {raw}")
        assert r.status_code == 200, r.content
        return r.json()

    def _no_customer_wide_trace(self, c):
        c.refresh_from_db()
        assert c.status == "active"                               # not suspended
        assert not Wallet.objects.filter(customer=c).exists()    # no wallet made
        assert Door.stop_reason(c.id) is None                     # no flag
        assert not StopSignalState.objects.filter(owner=c).exists()  # no episode
        assert not OutboxEvent.objects.filter(event_type__in=[
            CustomerStopped.EVENT_TYPE, "customer.suspended"]).exists()

    def test_a_priced_event_under_enforcing_opens_no_hard_floor(self):
        self._priced_events_open_no_hard_floor(self._external())

    def test_the_billing_product_on_an_external_tenant_changes_none_of_that(self):
        """`external + billing` is a valid posture (Stage A, 2026-11-02): the
        product brings the platform-fee period, the pools and the postpaid
        reads, and still no wallet — the same priced events, the same
        absence of every customer-wide trace."""
        self._priced_events_open_no_hard_floor(
            self._external(products=("metering", "billing")))

    def _priced_events_open_no_hard_floor(self, t):
        client = Client()
        _k, raw = TenantApiKey.create_key(t, label="t")
        c = Customer.objects.create(tenant=t, external_id="jim")
        a_rule_that_prices_what_it_measures(t)
        body = self._recorded(client, raw, c, "k1", measurements=priced_at(8_000_000))
        # The event IS priced — the stop it must not open would have been
        # opened by exactly this figure, so the assertion is not vacuous.
        assert body["pricing_status"] == "known"
        assert body["billed_cost_micros"] == 8_000_000
        assert body["stop"] is False and body["stop_reason"] is None
        assert Posting.objects.get(tenant=t, idempotency_key="k1").stop_context is None
        self._no_customer_wide_trace(c)
        # And a second one, which the flag a first one wrongly set would stop.
        again = self._recorded(client, raw, c, "k2", measurements=priced_at(8_000_000))
        assert again["stop"] is False and again["stop_reason"] is None
        # The start gate reads the same flag: new work is admitted.
        r = client.post("/api/v1/tasks", data=json.dumps({
            "customer_id": str(c.id), "idempotency_key": "t1"}),
            content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {raw}")
        assert r.status_code == 200, r.content

    def test_the_durable_drawdown_lane_makes_no_wallet_either(self):
        # The billing product enabled on an external tenant reaches the
        # drawdown handler; the drawdown is the wallet's and there is none.
        t = self._external(products=("metering", "billing"))
        c = Customer.objects.create(tenant=t, external_id="jim")
        handle_usage_recorded_billing(str(uuid.uuid4()), asdict(UsageRecorded(
            pricing_status_reason=None,
            tenant_id=t.id, customer_id=c.id,
            event_id=str(uuid.uuid4()), cost_micros=8_000_000)))
        self._no_customer_wide_trace(c)
        assert not OutboxEvent.objects.filter(event_type="wallet.balance_overage").exists()

    def test_the_credit_hook_and_reconcile_skip_the_wallet_leg(self):
        from apps.billing.gating.services.live_counter import LiveCounter
        t = self._external()
        c = Customer.objects.create(tenant=t, external_id="jim")
        assert LiveCounter.credit(c.id, t, 5_000_000) is None
        LiveCounter.reconcile(c.id, t)
        assert Door.balance(c.id) is None                         # never seeded
        self._no_customer_wide_trace(c)

    def test_a_units_ceiling_still_stops_the_unit(self, django_capture_on_commit_callbacks):
        from apps.platform.event_types.tests._helpers import (
            declares_a_caller_supplied_cost)
        client = Client()
        t = self._external()
        _k, raw = TenantApiKey.create_key(t, label="t")
        c = Customer.objects.create(tenant=t, external_id="jim")
        declares_a_caller_supplied_cost(t, "call")
        r = client.post("/api/v1/tasks", data=json.dumps({
            "customer_id": str(c.id), "idempotency_key": "t1",
            "task_cogs_ceiling_micros": 1_000}),
            content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {raw}")
        assert r.status_code == 200, r.content
        unit = r.json()["task_id"]
        under = self._recorded(client, raw, c, "u1", task_id=unit,
                               event_type="call", provider_cost_micros=600)
        assert under["stop"] is False
        # The kill itself is registered on commit (usage_service, the crossing
        # report's on-commit), so the callbacks run here as they would in life.
        with django_capture_on_commit_callbacks(execute=True):
            crossing = self._recorded(client, raw, c, "u2", task_id=unit,
                                      event_type="call", provider_cost_micros=600)
        assert crossing["stop"] is True
        assert crossing["stop_reason"] == reasons.TASK_COGS_CEILING
        assert crossing["stop_scope"] == "task"
        g = client.get(f"/api/v1/tasks/{unit}", HTTP_AUTHORIZATION=f"Bearer {raw}")
        assert g.json()["status"] == "killed"
        # The unit stopped; the customer did not.
        self._no_customer_wide_trace(c)


@pytest.mark.django_db
class TestAWalletExistsOnlyWhereOneIsHeld:
    """Stage A of the pre-Ash billing readiness (owner/consultant rulings of
    2026-11-02): a wallet exists only where `holds_a_wallet(tenant)` is true
    — `prepaid` in v1. `external` and `postpaid` have no wallet subject, with
    or without the `billing` product; an absent wallet is never a zero-balance
    wallet and is never lazily invented by a wallet operation. No second
    predicate is invented: every site below asks the kernel's one answer.

    What is pinned here, at the service seam: the boundary every mutation
    takes (`lock_for_billing`) refuses by name before any Wallet row is read
    or created; the money-shaped verdict runs no wallet lane for a no-wallet
    tenant while its standing, stop-flag and spend-pool checks still answer;
    a fixed-price start reserves nothing and is not refused; and no outbox
    handler, beat task or patrol leg that is gated upstream reaches the
    boundary — proven by a boundary that fails the test if reached, not by
    reading the gate. The route-level matrices live in the api/v1 suites,
    and the lanes that CAN meet the boundary (a tenant that left `prepaid`
    with rows behind) pin their recording in the Stripe connector's suites.
    """

    def setup_method(self):
        cache.clear()
        # `postpaid` is a money mode and needs its rail (G27); asked for by
        # name here, before any tenant is built. `external` needs none.
        activate_the_rail()

    def _tenant(self, mode, *, enf="off"):
        return Tenant.objects.create(name=mode, products=["metering", "billing"],
                                     billing_mode=mode, enforcement_mode=enf)

    def _no_wallet_rows(self, c):
        assert not Wallet.all_objects.filter(customer=c).exists()
        assert not WalletTransaction.objects.filter(wallet__customer=c).exists()
        assert not WalletReservation.objects.filter(tenant=c.tenant).exists()

    # --- the boundary ------------------------------------------------------

    @pytest.mark.parametrize("mode", NO_WALLET_MODES)
    def test_the_boundary_refuses_by_name_before_any_wallet_row(self, mode):
        t = self._tenant(mode)
        c = Customer.objects.create(tenant=t, external_id="jim")
        assert not holds_a_wallet(t)
        with pytest.raises(NoWalletSubjectError) as refused:
            with transaction.atomic():
                lock_for_billing(c.id)
        assert refused.value.billing_mode == mode
        # The detail names the MODE the wallet capability is absent in —
        # never the product, which this tenant holds.
        assert f"billing mode ({mode})" in str(refused.value)
        assert "product" not in str(refused.value)
        self._no_wallet_rows(c)

    def test_prepaid_still_mints_the_wallet_at_the_boundary(self):
        t = self._tenant("prepaid")
        c = Customer.objects.create(tenant=t, external_id="jim")
        assert holds_a_wallet(t)
        with transaction.atomic():
            wallet, owner = lock_for_billing(c.id)
        assert (wallet.customer_id, owner.id) == (c.id, c.id)
        assert (wallet.balance_micros, wallet.currency) == (0, t.default_currency)
        assert Wallet.objects.filter(customer=c).count() == 1

    # --- the money-shaped verdict ------------------------------------------

    @pytest.mark.parametrize("mode", NO_WALLET_MODES)
    def test_the_verdict_runs_no_wallet_lane_so_a_floor_refuses_nothing(self, mode):
        """A floor above zero — the one shape under which an absent wallet
        read as a zero balance IS past the line (`api/v1/tests/
        test_a_start_claims_its_key.py` pins that for `prepaid`) — refuses
        nothing here: there is no wallet to be past it, the floors are
        reported as not applying, and no episode or suspension follows."""
        t = self._tenant(mode, enf="enforcing")
        c = Customer.objects.create(tenant=t, external_id="jim")
        CustomerBillingProfile.objects.create(
            customer=c, min_balance_micros=-2_000_000,
            soft_min_balance_micros=-1_000_000)
        verdict = RiskService.check(c)
        assert (verdict["allowed"], verdict["reason"]) == (True, None)
        assert (verdict["min_balance_micros"],
                verdict["soft_min_balance_micros"]) == (None, None)
        c.refresh_from_db()
        assert c.status == "active"
        assert not StopSignalState.objects.filter(owner=c).exists()
        self._no_wallet_rows(c)

    @pytest.mark.parametrize("mode", NO_WALLET_MODES)
    def test_the_standing_and_the_spend_pool_still_answer_off_the_wallet_lane(self, mode):
        t = self._tenant(mode)
        c = Customer.objects.create(tenant=t, external_id="jim")
        CustomerSpendPool.objects.create(tenant=t, customer=c, cap_micros=1_000,
                                         enforce_mode="blocking")
        a_posting(tenant=t, customer=c, idempotency_key="i",
                  provider_cost_micros=1_000, billed_cost_micros=1_000)
        LiveCounter.spend_pool_incr(t.id, c.id, 1_000)
        pooled = RiskService.check(c)
        assert (pooled["allowed"], pooled["reason"]) == (
            False, AFFORDABILITY_REASON_CUSTOMER_SPEND_POOL_EXCEEDED)
        suspended = Customer.objects.create(tenant=t, external_id="sue",
                                            status="suspended")
        assert RiskService.check(suspended)["allowed"] is False
        self._no_wallet_rows(c)

    @pytest.mark.parametrize("mode", NO_WALLET_MODES)
    def test_a_fixed_price_start_reserves_nothing_and_is_not_refused(self, mode):
        """The reservation half answers the EMPTY verdict — allowed, nothing
        read — before the boundary: the start is legitimate, only the
        reservation has no subject, so a refusal exception here would be
        wrong and none is raised."""
        t = self._tenant(mode)
        c = Customer.objects.create(tenant=t, external_id="jim")
        unit = SimpleNamespace(agreed_price_micros=5_000_000, billing_owner_id=c.id)
        with transaction.atomic():
            verdict = RiskService.reserve_agreed_price(c, unit)
        assert verdict == {"allowed": True, "reason": None,
                           "balance_micros": None, "available_micros": None,
                           "min_balance_micros": None,
                           "soft_min_balance_micros": None}
        self._no_wallet_rows(c)

    # --- the lanes gated upstream never reach the boundary ------------------

    @pytest.mark.parametrize("mode", NO_WALLET_MODES)
    def test_no_gated_lane_reaches_the_boundary(self, mode, monkeypatch):
        """The drawdown handler, the reconcile's wallet pass, the upward
        repair and the beat's per-owner loop each ask `holds_a_wallet`
        before the lock. Proven by a boundary that FAILS the test if any of
        them reaches it, driven once each for a no-wallet tenant under
        `enforcing` — and the platform-fee period still accrues the event,
        because billing the tenant for its usage asks no wallet."""
        t = self._tenant(mode, enf="enforcing")
        c = Customer.objects.create(tenant=t, external_id="jim")
        posting = a_posting(tenant=t, customer=c, idempotency_key="i1",
                            provider_cost_micros=1_000, billed_cost_micros=8_000_000)

        def reached(customer_id):
            raise AssertionError(f"the wallet boundary was reached for {customer_id}")
        monkeypatch.setattr("apps.billing.locking.lock_for_billing", reached)

        handle_usage_recorded_billing(str(uuid.uuid4()), asdict(UsageRecorded(
            pricing_status_reason=None, tenant_id=t.id, customer_id=c.id,
            event_id=str(posting.id), cost_micros=8_000_000)))
        LiveCounter.reconcile(c.id, t)
        assert repair_live_balances(t)[OUTCOME_REPAIRED] == 0
        _per_owner_reconcile(t)

        self._no_wallet_rows(c)
        period = TenantBillingPeriod.objects.get(tenant=t)
        assert (period.total_billed_cost_micros, period.recorded_events) == (8_000_000, 1)
