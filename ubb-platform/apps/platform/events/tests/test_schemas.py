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
        event = UsageRecorded.from_payload(d)
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


# --- #114: the consumer half of the frozen contract lives on the base class ---


class TestFromPayload:
    def test_unknown_keys_are_filtered(self):
        # Additive-only evolution: a NEWER producer's extra field must not
        # break an older consumer constructing from the payload.
        from apps.platform.events.schemas import UsageRecorded

        event = UsageRecorded.from_payload({
            "tenant_id": "t1", "customer_id": "c1", "event_id": "e1",
            "cost_micros": 500, "some_future_field": "ignored",
        })
        assert event.cost_micros == 500
        assert not hasattr(event, "some_future_field")

    def test_defaults_are_defined_once_on_the_class(self):
        # A legacy queued payload written before a field existed constructs
        # with the class default — no consumer restates it.
        from apps.platform.events.schemas import UsageRecorded

        event = UsageRecorded.from_payload({
            "tenant_id": "t1", "customer_id": "c1", "event_id": "e1",
            "cost_micros": 500,
        })
        assert event.provider_cost_micros is None
        assert event.billing_owner_id == ""
        assert event.effective_at == ""

    def test_missing_required_field_is_loud(self):
        # Required-since-birth fields have no default: a payload without one
        # is malformed and must not construct half-initialized.
        import pytest
        from apps.platform.events.schemas import UsageRecorded

        with pytest.raises(TypeError):
            UsageRecorded.from_payload({"tenant_id": "t1"})

    def test_roundtrips_the_producer_side(self):
        from dataclasses import asdict
        from apps.platform.events.schemas import StopFired

        produced = StopFired(tenant_id="t1", owner_id="o1", reason="floor",
                             episode_seq=3)
        assert StopFired.from_payload(asdict(produced)) == produced


class TestUuidOrStrIds:
    def test_uuid_ids_are_accepted_and_normalized_to_str(self):
        import uuid
        from apps.platform.events.schemas import UsageRecorded

        tid, cid = uuid.uuid4(), uuid.uuid4()
        event = UsageRecorded(tenant_id=tid, customer_id=cid, event_id="e1",
                              cost_micros=1)
        assert event.tenant_id == str(tid)
        assert event.customer_id == str(cid)

    def test_asdict_payload_stays_json_serializable(self):
        import json
        import uuid
        from dataclasses import asdict
        from apps.platform.events.schemas import UsageRecorded

        event = UsageRecorded(tenant_id=uuid.uuid4(), customer_id=uuid.uuid4(),
                              event_id=uuid.uuid4(), cost_micros=1)
        json.dumps(asdict(event))  # raises on a stray UUID


class TestPayloadSchemaRegistry:
    def test_registry_holds_every_dataclass_defined_in_the_module(self):
        # Independent enumeration (defense in depth for the catalog
        # derivation): every frozen dataclass defined in schemas.py must have
        # registered itself via the base class.
        import dataclasses
        import inspect
        from apps.platform.events import schemas
        from apps.platform.events.schemas import payload_schema_classes

        defined = {
            obj
            for obj in vars(schemas).values()
            if inspect.isclass(obj)
            and obj.__module__ == schemas.__name__
            and dataclasses.is_dataclass(obj)
        }
        assert defined == set(payload_schema_classes())

    def test_registered_classes_are_keyed_by_unique_event_type(self):
        from apps.platform.events.schemas import payload_schema_classes

        event_types = [cls.EVENT_TYPE for cls in payload_schema_classes()]
        assert len(event_types) == len(set(event_types))

    def test_duplicate_event_type_is_a_class_creation_error(self):
        # Uses an EXISTING event type so the rejected class never registers —
        # no registry pollution for later tests.
        import pytest
        from apps.platform.events.schemas import EventSchema

        with pytest.raises(TypeError, match="usage.recorded"):
            class Dupe(EventSchema):
                EVENT_TYPE = "usage.recorded"

    def test_schema_without_event_type_is_a_class_creation_error(self):
        # The old pin turned a missing EVENT_TYPE into a red test; the base
        # class turns it into an error at class creation.
        import pytest
        from apps.platform.events.schemas import EventSchema

        with pytest.raises(TypeError, match="EVENT_TYPE"):
            class Missing(EventSchema):
                tenant_id: str
