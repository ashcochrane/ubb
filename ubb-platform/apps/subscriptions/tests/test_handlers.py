import threading
from unittest.mock import patch

import pytest
from dataclasses import asdict
from django.db import connection, transaction
from django.test import TransactionTestCase
from django.utils import timezone
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.platform.events.schemas import UsageRecorded


@pytest.mark.django_db
class TestHandleUsageRecorded:
    def test_creates_accumulator_on_first_event(self):
        from apps.subscriptions.handlers import handle_usage_recorded_subscriptions
        from apps.subscriptions.economics.models import CustomerCostAccumulator

        tenant = Tenant.objects.create(name="test", products=["metering", "billing"])
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")

        handle_usage_recorded_subscriptions("evt-outbox-1", asdict(UsageRecorded(
            pricing_status_reason=None,
            tenant_id=tenant.id,
            customer_id=customer.id,
            cost_micros=1_500_000,
            provider_cost_micros=1_200_000,
            billed_cost_micros=1_500_000,
            event_type="api_call",
            event_id="evt-1",
        )))

        acc = CustomerCostAccumulator.objects.get(tenant=tenant, customer=customer)
        assert acc.total_provider_cost_micros == 1_200_000
        assert acc.total_billed_cost_micros == 1_500_000
        assert acc.posting_count == 1

    def test_accumulates_on_subsequent_events(self):
        from apps.subscriptions.handlers import handle_usage_recorded_subscriptions
        from apps.subscriptions.economics.models import CustomerCostAccumulator

        tenant = Tenant.objects.create(name="test", products=["metering", "billing"])
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")

        for i in range(3):
            handle_usage_recorded_subscriptions(f"evt-outbox-{i}", asdict(UsageRecorded(
                pricing_status_reason=None,
                tenant_id=tenant.id,
                customer_id=customer.id,
                cost_micros=1_000_000,
                provider_cost_micros=800_000,
                billed_cost_micros=1_000_000,
                event_type="api_call",
                event_id=f"evt-{i}",
            )))

        acc = CustomerCostAccumulator.objects.get(tenant=tenant, customer=customer)
        assert acc.total_provider_cost_micros == 2_400_000
        assert acc.total_billed_cost_micros == 3_000_000
        assert acc.posting_count == 3

    def test_a_zero_event_is_counted_rather_than_skipped(self):
        """#603 ruling 9: zero is a real known value. This pinned the opposite
        until #603 — a zero/zero event was skipped, and the period's event
        count missed it until the hourly reconcile repaired it."""
        from apps.subscriptions.handlers import handle_usage_recorded_subscriptions
        from apps.subscriptions.economics.models import CustomerCostAccumulator

        tenant = Tenant.objects.create(name="test", products=["metering", "billing"])
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")

        handle_usage_recorded_subscriptions("evt-outbox-0", asdict(UsageRecorded(
            pricing_status_reason=None,
            tenant_id=tenant.id,
            customer_id=customer.id,
            cost_micros=0,
            provider_cost_micros=0,
            billed_cost_micros=0,
            event_type="api_call",
            event_id="evt-0",
        )))

        acc = CustomerCostAccumulator.objects.get(tenant=tenant, customer=customer)
        assert acc.total_provider_cost_micros == 0
        assert acc.total_billed_cost_micros == 0
        assert acc.posting_count == 1

    def test_a_negative_known_cost_is_carried(self):
        """A negative supplier cost is one the records hold faithfully (#603
        ruling 8): the period's COGS carries it rather than dropping it."""
        from apps.subscriptions.handlers import handle_usage_recorded_subscriptions
        from apps.subscriptions.economics.models import CustomerCostAccumulator

        tenant = Tenant.objects.create(name="test", products=["metering", "billing"])
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")

        handle_usage_recorded_subscriptions("evt-outbox-n", asdict(UsageRecorded(
            pricing_status_reason=None,
            tenant_id=tenant.id,
            customer_id=customer.id,
            cost_micros=0,
            provider_cost_micros=-300_000,
            billed_cost_micros=0,
            event_type="api_call",
            event_id="evt-n",
        )))

        acc = CustomerCostAccumulator.objects.get(tenant=tenant, customer=customer)
        assert acc.total_provider_cost_micros == -300_000
        assert acc.posting_count == 1

    def test_handler_accumulates_provider_and_billed(self):
        from apps.subscriptions.handlers import handle_usage_recorded_subscriptions
        from apps.subscriptions.economics.models import CustomerCostAccumulator

        tenant = Tenant.objects.create(name="test2", products=["metering", "billing"])
        customer = Customer.objects.create(tenant=tenant, external_id="cust-2")

        handle_usage_recorded_subscriptions("evt1", asdict(UsageRecorded(
            pricing_status_reason=None,
            tenant_id=tenant.id, customer_id=customer.id,
            event_id="evt-1", cost_micros=1_000_000,
            provider_cost_micros=800_000, billed_cost_micros=1_000_000)))
        acc = CustomerCostAccumulator.objects.get(tenant=tenant, customer=customer)
        assert acc.total_provider_cost_micros == 800_000
        assert acc.total_billed_cost_micros == 1_000_000
        assert acc.posting_count == 1

    def test_handler_accumulates_twice(self):
        from apps.subscriptions.handlers import handle_usage_recorded_subscriptions
        from apps.subscriptions.economics.models import CustomerCostAccumulator

        tenant = Tenant.objects.create(name="test3", products=["metering", "billing"])
        customer = Customer.objects.create(tenant=tenant, external_id="cust-3")

        for _ in range(2):
            handle_usage_recorded_subscriptions("evt2", asdict(UsageRecorded(
                pricing_status_reason=None,
                tenant_id=tenant.id, customer_id=customer.id,
                event_id="evt-2", cost_micros=1_000_000,
                provider_cost_micros=800_000, billed_cost_micros=1_000_000)))

        acc = CustomerCostAccumulator.objects.get(tenant=tenant, customer=customer)
        assert acc.total_provider_cost_micros == 1_600_000
        assert acc.total_billed_cost_micros == 2_000_000
        assert acc.posting_count == 2


class TestTwoRacingFirstEventsOfAPeriod(TransactionTestCase):
    """W7 preparation finding F6, ruled 2026-10-30: concurrent first events for
    one customer can neither abort economic accumulation nor double-count it.

    Two threads, two PostgreSQL connections, one customer with no accumulator
    row yet. A barrier inside the manager's `create` holds both threads AFTER
    each has seen the UPDATE touch 0 rows and BEFORE either inserts, so both
    insert: the winner commits its row, the loser's INSERT fails the unique
    constraint and must resolve to the winner's row and add its increment
    exactly once. Before the fix the loser's fallback UPDATE ran in a
    transaction PostgreSQL had already aborted — `TransactionManagementError`,
    the handler failed, and only the outbox retry repaired it.
    """

    def test_the_loser_resolves_the_winners_row_and_adds_exactly_once(self):
        from apps.subscriptions.economics.models import CustomerCostAccumulator
        from apps.subscriptions.handlers import handle_usage_recorded_subscriptions

        tenant = Tenant.objects.create(name="race", products=["metering", "billing"])
        customer = Customer.objects.create(tenant=tenant, external_id="cust-race")
        manager = CustomerCostAccumulator.objects
        real_create = manager.create
        at_the_insert = threading.Barrier(2, timeout=15)
        errors = []

        def racing_create(**fields):
            at_the_insert.wait()
            return real_create(**fields)

        def one_first_event(n):
            try:
                with transaction.atomic():   # the dispatcher's transaction
                    handle_usage_recorded_subscriptions(f"race-{n}", asdict(UsageRecorded(
                        pricing_status_reason=None,
                        tenant_id=tenant.id, customer_id=customer.id,
                        event_id=f"evt-race-{n}", cost_micros=1_000_000,
                        provider_cost_micros=800_000, billed_cost_micros=1_000_000)))
            except Exception as exc:  # noqa: BLE001 — the failure IS the finding
                errors.append(repr(exc))
            finally:
                connection.close()

        with patch.object(manager, "create", racing_create):
            threads = [threading.Thread(target=one_first_event, args=(n,)) for n in (1, 2)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=30)

        assert errors == [], errors
        rows = list(CustomerCostAccumulator.objects.filter(tenant=tenant, customer=customer))
        assert len(rows) == 1
        assert rows[0].posting_count == 2
        assert rows[0].total_provider_cost_micros == 1_600_000
        assert rows[0].total_billed_cost_micros == 2_000_000
