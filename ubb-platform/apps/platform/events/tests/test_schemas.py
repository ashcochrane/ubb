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
