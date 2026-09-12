from django.core.cache import cache
from django.test import TestCase
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.platform.work import admission
from apps.billing.gating.models import RiskConfig
from apps.billing.gating.services.risk_service import RiskService
from apps.billing.tenant_billing.models import BillingTenantConfig
from apps.billing.wallets.models import CustomerBillingProfile, Wallet
from core.vocabulary import AFFORDABILITY_REASON_CUSTOMER_SPEND_POOL_EXCEEDED


class RiskServiceTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="u1")
        RiskConfig.objects.create(tenant=self.tenant)

    def test_active_customer_passes(self):
        result = RiskService.check(self.customer)
        self.assertTrue(result["allowed"])

    def test_suspended_customer_blocked(self):
        self.customer.status = "suspended"
        self.customer.save()
        result = RiskService.check(self.customer)
        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason"], "insufficient_funds")

    def test_closed_customer_blocked(self):
        self.customer.status = "closed"
        self.customer.save()
        result = RiskService.check(self.customer)
        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason"], "account_closed")

    def test_no_risk_config_passes(self):
        """The risk row holds the pool read's fail-closed posture and nothing
        else (#462); a tenant without one is answered like any other."""
        RiskConfig.objects.all().delete()
        result = RiskService.check(self.customer)
        self.assertTrue(result["allowed"])

    def test_returns_balance_micros(self):
        Wallet.objects.create(customer=self.customer, balance_micros=5_000_000)
        result = RiskService.check(self.customer)
        self.assertTrue(result["allowed"])
        self.assertEqual(result["balance_micros"], 5_000_000)

    def test_no_wallet_defaults_balance_to_zero(self):
        result = RiskService.check(self.customer)
        self.assertTrue(result["allowed"])
        self.assertEqual(result["balance_micros"], 0)

    def test_affordability_denied_when_balance_below_negative_threshold(self):
        """Deny when balance < -min_balance."""
        # Tenant default min_balance is 0
        # balance(-6M) < -0 → denied
        Wallet.objects.create(customer=self.customer, balance_micros=-6_000_000)
        result = RiskService.check(self.customer)
        self.assertFalse(result["allowed"])
        self.assertEqual(result["reason"], "insufficient_funds")
        self.assertEqual(result["balance_micros"], -6_000_000)

    def test_affordability_allowed_within_min_balance(self):
        """Allow when balance >= -min_balance (custom threshold)."""
        BillingTenantConfig.objects.create(
            tenant=self.tenant, min_balance_micros=5_000_000,
        )
        Wallet.objects.create(customer=self.customer, balance_micros=-3_000_000)
        result = RiskService.check(self.customer)
        self.assertTrue(result["allowed"])
        self.assertEqual(result["balance_micros"], -3_000_000)

    def test_affordability_allowed_positive_balance(self):
        """Positive balance is always allowed."""
        Wallet.objects.create(customer=self.customer, balance_micros=100)
        result = RiskService.check(self.customer)
        self.assertTrue(result["allowed"])
        self.assertEqual(result["balance_micros"], 100)

    def test_affordability_denied_no_wallet_zero_threshold(self):
        """No wallet (balance=0), zero threshold: balance(0) < -0 is false → allowed."""
        CustomerBillingProfile.objects.create(
            customer=self.customer, min_balance_micros=0,
        )
        result = RiskService.check(self.customer)
        self.assertTrue(result["allowed"])
        self.assertEqual(result["balance_micros"], 0)

    def test_the_answer_names_no_unit_of_work(self):
        """It used to answer with a null identifier for the unit it had not
        created; it answers with no such key at all now (#410). A whole set
        rather than one absent key: an answer that quietly grew a member
        naming a unit would be a registration riding back on an advisory
        call, which is the shape this route was split to remove. The fourth
        member it DID grow (#461) is a money figure — the balance less open
        reservations, which is what the floors are compared against — and
        the set is pinned again here so the next arrival is read by a person.
        """
        result = RiskService.check(self.customer)
        self.assertEqual(set(result), {"allowed", "reason", "balance_micros",
                                       "available_micros"})

    def test_asking_the_verdict_twice_moves_no_admission_window(self):
        """The advisory question consumes nothing (#462, slice 6 §6, TD
        claim 8): the per-minute bound on new work left this verdict for
        the kernel, so asking it — however often — neither counts a start
        nor refuses one. Pinned against the kernel's own window: a bound of
        one, two questions, and the seat's window still empty, so the one
        start the bound admits is still there to be admitted. Ticket 12
        asserts this again on the renamed call."""
        self.tenant.max_task_starts_per_minute = 1
        self.tenant.save(update_fields=["max_task_starts_per_minute"])
        starts_key, _ = admission.window_keys(self.customer.id)
        self.assertTrue(RiskService.check(self.customer)["allowed"])
        self.assertTrue(RiskService.check(self.customer)["allowed"])
        self.assertIsNone(cache.get(starts_key))
        self.assertEqual(
            admission.admit(self.tenant, self.customer, contained=False).remaining, 0)


# ⚠ `RiskServiceRedisFailureTest` STOOD HERE AND ITS SUBJECT MOVED WHOLE
# (#462). Its one case — that the throttle fails open when its store is away
# — was about the per-minute bound, which is the kernel's admission check
# now; `apps/platform/work/tests/test_admission_control.py` holds the case
# at the store the bound actually reads. Nothing in this verdict touches
# the Django cache any more.


# ⚠ `RiskServiceTaskTest` STOOD HERE AND ITS SUBJECT MOVED WHOLE (#410).
# Seven cases, every one of them about the unit of work this service created
# behind a flag: that it was born active, that it snapshotted the wallet
# balance, that an explicit ceiling and a tenant default each landed on the
# row, that a denied answer created nothing, that the flagless call created
# nothing, and that the caller's metadata and label were carried onto it.
#
# This service registers nothing now — `POST /api/v1/tasks` does, at the root
# and behind no product gate — so the cases went with the behaviour rather
# than being deleted. `api/v1/tests/test_a_start_claims_its_key.py` holds the
# balance snapshot, the uncapped default, the ceiling carried through, the
# refusal that creates nothing, the metadata and the label, and this service's
# own half (that the advisory call registers nothing at all);
# `api/v1/tests/test_one_rule_pins.py` holds the tenant default rung and
# `api/v1/tests/test_the_ceiling_belongs_to_the_kind_of_work.py` the rest of
# the ladder.


import pytest
from django.core.cache import cache as django_cache
from apps.billing.gating.models import CustomerSpendPool
from apps.billing.gating.services.live_counter import LiveCounter


@pytest.mark.django_db
class TestRiskServiceCustomerSpendPool:
    def setup_method(self):
        django_cache.clear()

    def _funded(self, **cfg):
        from apps.platform.tenants.models import Tenant
        from apps.platform.customers.models import Customer
        from apps.billing.wallets.models import Wallet
        t = Tenant.objects.create(name="T", products=["metering", "billing"])
        c = Customer.objects.create(tenant=t, external_id="c1")
        w = Wallet.objects.create(customer=c)
        w.balance_micros = 10_000_000  # plenty — affordability passes
        w.save(update_fields=["balance_micros"])
        if cfg:
            CustomerSpendPool.objects.create(tenant=t, customer=c, **cfg)
        return c

    def _spend(self, c, amount):
        from apps.metering.usage.models import Posting
        Posting.objects.create(tenant=c.tenant, customer=c, idempotency_key="i",
                                  provider_cost_micros=amount, billed_cost_micros=amount)
        LiveCounter.spend_pool_incr(c.tenant_id, c.id, amount)

    def test_no_budget_config_allows(self):
        c = self._funded()
        assert RiskService.check(c)["allowed"] is True

    def test_blocking_over_cap_denies(self):
        c = self._funded(cap_micros=1_000, enforce_mode="blocking", hard_stop_pct=100)
        self._spend(c, 1_000)  # at cap
        res = RiskService.check(c)
        assert res["allowed"] is False
        assert res["reason"] == AFFORDABILITY_REASON_CUSTOMER_SPEND_POOL_EXCEEDED

    def test_alert_only_over_cap_allows(self):
        c = self._funded(cap_micros=1_000, enforce_mode="alert_only")
        self._spend(c, 5_000)  # way over
        assert RiskService.check(c)["allowed"] is True

    def test_gate_fail_open_when_redis_down_with_budget_config(self):
        # Even with a blocking pool declared, a Redis outage must NOT block the
        # pre-call gate — the money is still guarded by the Postgres credit check.
        from unittest.mock import patch
        c = self._funded(cap_micros=1_000, enforce_mode="blocking")
        with patch("apps.billing.gating.services.live_counter._client",
                   side_effect=ConnectionError("redis down")):
            res = RiskService.check(c)
        assert res["allowed"] is True

    def test_postpaid_negative_balance_still_allowed(self):
        from apps.platform.tenants.models import Tenant
        from apps.platform.customers.models import Customer
        from apps.billing.wallets.models import Wallet
        t = Tenant.objects.create(name="PP", products=["metering", "billing"], billing_mode="postpaid")
        c = Customer.objects.create(tenant=t, external_id="pp")
        Wallet.objects.create(customer=c, balance_micros=-9_999_999)  # deep negative
        assert RiskService.check(c)["allowed"] is True  # postpaid never gates on credit balance

    def test_postpaid_budget_cap_still_enforced(self):
        from apps.platform.tenants.models import Tenant
        from apps.platform.customers.models import Customer
        from apps.metering.usage.models import Posting
        t = Tenant.objects.create(name="PP", products=["metering", "billing"], billing_mode="postpaid")
        c = Customer.objects.create(tenant=t, external_id="pp")
        CustomerSpendPool.objects.create(tenant=t, customer=c, cap_micros=1_000, enforce_mode="blocking")
        Posting.objects.create(tenant=t, customer=c, idempotency_key="i",
                                  provider_cost_micros=1_000, billed_cost_micros=1_000)
        LiveCounter.spend_pool_incr(t.id, c.id, 1_000)
        res = RiskService.check(c)
        assert res["allowed"] is False
        assert res["reason"] == AFFORDABILITY_REASON_CUSTOMER_SPEND_POOL_EXCEEDED

    def test_suspended_business_gates_its_seat(self):
        from apps.platform.tenants.models import Tenant
        from apps.platform.customers.models import Customer
        from apps.billing.wallets.models import Wallet
        t = Tenant.objects.create(name="PB", products=["metering", "billing"], billing_mode="prepaid")
        biz = Customer.objects.create(tenant=t, external_id="biz", account_type="business",
                                      billing_topology="pooled", status="suspended")
        seat = Customer.objects.create(tenant=t, external_id="s1", account_type="seat", parent=biz)
        Wallet.objects.create(customer=biz, balance_micros=10_000_000)
        res = RiskService.check(seat)
        assert res["allowed"] is False and res["reason"] == "insufficient_funds"

    def test_pooled_seat_affordability_reads_business_wallet(self):
        from apps.platform.tenants.models import Tenant
        from apps.platform.customers.models import Customer
        from apps.billing.wallets.models import Wallet
        t = Tenant.objects.create(name="PB", products=["metering", "billing"], billing_mode="prepaid")
        biz = Customer.objects.create(tenant=t, external_id="biz", account_type="business",
                                      billing_topology="pooled")
        seat = Customer.objects.create(tenant=t, external_id="s1", account_type="seat", parent=biz)
        Wallet.objects.create(customer=biz, balance_micros=-9_999_999)  # business pool deep negative
        assert RiskService.check(seat)["allowed"] is False
