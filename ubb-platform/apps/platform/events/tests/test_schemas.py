# ubb-platform/apps/platform/events/tests/test_schemas.py
from dataclasses import asdict


class TestUsageRecordedSchema:
    def test_create_with_required_fields(self):
        from apps.platform.events.schemas import UsageRecorded

        event = UsageRecorded(
            tenant_id="t1",
            customer_id="c1",
            event_id="e1",
            cost_micros=5000,
        )
        assert event.tenant_id == "t1"
        assert event.cost_micros == 5000
        assert event.provider_cost_micros is None
        assert event.billed_cost_micros is None
        assert event.event_type == ""
        assert event.provider == ""

    def test_frozen(self):
        from apps.platform.events.schemas import UsageRecorded
        import pytest

        event = UsageRecorded(tenant_id="t1", customer_id="c1", event_id="e1", cost_micros=5000)
        with pytest.raises(AttributeError):
            event.cost_micros = 999

    def test_roundtrip_via_dict(self):
        from apps.platform.events.schemas import UsageRecorded

        event = UsageRecorded(
            tenant_id="t1", customer_id="c1", event_id="e1",
            cost_micros=5000, billed_cost_micros=6000,
        )
        d = asdict(event)
        reconstructed = UsageRecorded(**d)
        assert reconstructed == event

    def test_extra_fields_ignored_gracefully(self):
        """New fields added later don't break old consumers."""
        from apps.platform.events.schemas import UsageRecorded

        d = {
            "tenant_id": "t1", "customer_id": "c1", "event_id": "e1",
            "cost_micros": 5000, "some_new_field": "value",
        }
        import dataclasses
        known = {f.name for f in dataclasses.fields(UsageRecorded)}
        filtered = {k: v for k, v in d.items() if k in known}
        event = UsageRecorded(**filtered)
        assert event.cost_micros == 5000


class TestUsageRefundedSchema:
    def test_create(self):
        from apps.platform.events.schemas import UsageRefunded

        event = UsageRefunded(
            tenant_id="t1", customer_id="c1", event_id="e1",
            refund_id="r1", refund_amount_micros=5000,
        )
        assert event.EVENT_TYPE == "usage.refunded"
        assert event.refund_amount_micros == 5000


class TestReferralRewardEarnedSchema:
    def test_create(self):
        from apps.platform.events.schemas import ReferralRewardEarned

        event = ReferralRewardEarned(
            tenant_id="t1", referral_id="ref1", referrer_id="rr1",
            referred_customer_id="c1", reward_micros=500,
        )
        assert event.EVENT_TYPE == "referral.reward_earned"


class TestBalanceLowSchema:
    def test_event_type(self):
        from apps.platform.events.schemas import BalanceLow
        assert BalanceLow.EVENT_TYPE == "billing.balance_low"

    def test_fields(self):
        from apps.platform.events.schemas import BalanceLow
        event = BalanceLow(
            tenant_id="t1",
            customer_id="c1",
            balance_micros=-1000000,
            threshold_micros=5000000,
            suggested_topup_micros=20000000,
        )
        assert event.balance_micros == -1000000
        assert event.suggested_topup_micros == 20000000


class TestBalanceCriticalSchema:
    def test_event_type(self):
        from apps.platform.events.schemas import BalanceCritical
        assert BalanceCritical.EVENT_TYPE == "billing.balance_critical"

    def test_fields(self):
        from apps.platform.events.schemas import BalanceCritical
        event = BalanceCritical(
            tenant_id="t1",
            customer_id="c1",
            balance_micros=-4500000,
            min_balance_micros=5000000,
        )
        assert event.min_balance_micros == 5000000


class TestTopUpRequestedSchema:
    def test_event_type(self):
        from apps.platform.events.schemas import TopUpRequested
        assert TopUpRequested.EVENT_TYPE == "billing.topup_requested"

    def test_fields(self):
        from apps.platform.events.schemas import TopUpRequested
        event = TopUpRequested(
            tenant_id="t1",
            customer_id="c1",
            amount_micros=20000000,
            trigger="auto",
            success_url="",
            cancel_url="",
        )
        assert event.trigger == "auto"


class TestCustomerSuspendedSchema:
    def test_event_type(self):
        from apps.platform.events.schemas import CustomerSuspended
        assert CustomerSuspended.EVENT_TYPE == "billing.customer_suspended"

    def test_fields(self):
        from apps.platform.events.schemas import CustomerSuspended
        event = CustomerSuspended(
            tenant_id="t1",
            customer_id="c1",
            reason="min_balance_exceeded",
            balance_micros=-5100000,
        )
        assert event.reason == "min_balance_exceeded"


class TestMarginEventContracts:
    def test_margin_event_contracts(self):
        from dataclasses import asdict
        from apps.platform.events.schemas import MarginCustomerUnprofitable, MarginProviderCostSpike
        e1 = MarginCustomerUnprofitable(
            tenant_id="t", customer_id="c", period_start="2026-06-01",
            gross_margin_micros=-500, margin_pct=-5.0, threshold_pct=0.0)
        assert e1.EVENT_TYPE == "margin.customer_unprofitable"
        assert asdict(e1)["customer_id"] == "c"
        e2 = MarginProviderCostSpike(
            tenant_id="t", customer_id="c", period_start="2026-06-01",
            prev_provider_cost_micros=100, current_provider_cost_micros=200,
            prev_margin_pct=20.0, current_margin_pct=5.0)
        assert e2.EVENT_TYPE == "margin.provider_cost_spike"


def test_budget_threshold_event_contract():
    from dataclasses import asdict
    from apps.platform.events.schemas import BudgetThresholdReached
    e = BudgetThresholdReached(tenant_id="t", customer_id="c", period="2026-06",
                               level=80, spend_micros=800, cap_micros=1000, enforce_mode="advisory")
    assert e.EVENT_TYPE == "budget.threshold_reached"
    assert asdict(e)["level"] == 80


def test_usage_invoice_pushed_contract():
    from dataclasses import asdict
    from apps.platform.events.schemas import UsageInvoicePushed
    e = UsageInvoicePushed(tenant_id="t", customer_id="c", period_start="2026-06",
                           total_billed_micros=1000, line_item_count=2, stripe_invoice_id="in_1")
    assert e.EVENT_TYPE == "usage.invoice_pushed"
    assert asdict(e)["line_item_count"] == 2


def test_auto_topup_requires_action_contract():
    from dataclasses import asdict
    from apps.platform.events.schemas import AutoTopupRequiresAction
    e = AutoTopupRequiresAction(tenant_id="t", customer_id="c", attempt_id="a",
                                amount_micros=20_000_000, code="authentication_required")
    assert e.EVENT_TYPE == "auto_topup.requires_action"
    assert asdict(e)["amount_micros"] == 20_000_000


def test_balance_overage_contract():
    from dataclasses import asdict
    from apps.platform.events.schemas import BalanceOverage
    e = BalanceOverage(tenant_id="t", customer_id="c", balance_micros=-500,
                       overage_limit_micros=0, overage_micros=500)
    assert e.EVENT_TYPE == "billing.balance_overage"
    assert asdict(e)["overage_micros"] == 500
