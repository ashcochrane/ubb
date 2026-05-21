from django.db import IntegrityError
from django.test import TestCase

from apps.metering.pricing.models import Card
from apps.metering.usage.models import EventBatch
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
from apps.metering.usage.models import UsageEvent


class UsageEventModelTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test")
        self.customer = Customer.objects.create(
            tenant=self.tenant,
            external_id="user_1",
        )

    def test_create_event(self):
        event = UsageEvent.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_abc123",
            idempotency_key="idem_abc123",
            cost_micros=500_000,
        )
        self.assertEqual(event.cost_micros, 500_000)
        self.assertEqual(event.request_id, "req_abc123")
        self.assertIsNotNone(event.effective_at)

    def test_event_immutability_save(self):
        event = UsageEvent.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_abc123",
            idempotency_key="idem_abc123",
            cost_micros=500_000,
        )
        event.cost_micros = 999_999
        with self.assertRaises(ValueError):
            event.save()

    def test_event_immutability_delete(self):
        event = UsageEvent.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_abc123",
            idempotency_key="idem_abc123",
            cost_micros=500_000,
        )
        with self.assertRaises(ValueError):
            event.delete()

    def test_idempotency_constraint(self):
        UsageEvent.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_abc123",
            idempotency_key="idem_duplicate",
            cost_micros=500_000,
        )
        with self.assertRaises(IntegrityError):
            UsageEvent.objects.create(
                tenant=self.tenant,
                customer=self.customer,
                request_id="req_def456",
                idempotency_key="idem_duplicate",
                cost_micros=300_000,
            )


class UsageEventCardFKTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        self.card = Card.objects.create(
            tenant=self.tenant,
            name="Gemini Flash",
            slug="gemini_flash",
            provider="google",
        )

    def test_event_with_card_fk(self):
        event = UsageEvent.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_1",
            idempotency_key="idem_1",
            cost_micros=1000,
            card=self.card,
        )
        event.refresh_from_db()
        self.assertEqual(event.card_id, self.card.id)

    def test_event_card_nullable(self):
        event = UsageEvent.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_2",
            idempotency_key="idem_2",
            cost_micros=1000,
        )
        self.assertIsNone(event.card)

    def test_event_card_set_null_on_delete(self):
        event = UsageEvent.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_3",
            idempotency_key="idem_3",
            cost_micros=1000,
            card=self.card,
        )
        Card.objects.filter(id=self.card.id).delete()
        event.refresh_from_db()
        self.assertIsNone(event.card)


class EventBatchTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")

    def test_create_batch(self):
        batch = EventBatch.objects.create(
            tenant=self.tenant,
            action="added",
            reason="Monthly import",
            row_count=150,
            author="user@example.com",
        )
        batch.refresh_from_db()
        self.assertEqual(batch.action, "added")
        self.assertEqual(batch.row_count, 150)
        self.assertIsNone(batch.reversed_at)

    def test_event_linked_to_batch(self):
        batch = EventBatch.objects.create(
            tenant=self.tenant,
            action="added",
            reason="Import",
            row_count=1,
            author="user@example.com",
        )
        event = UsageEvent.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_batch",
            idempotency_key="idem_batch",
            cost_micros=1000,
            batch=batch,
        )
        self.assertEqual(event.batch_id, batch.id)
        self.assertEqual(batch.events.count(), 1)

    def test_batch_nullable_on_event(self):
        event = UsageEvent.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_no_batch",
            idempotency_key="idem_no_batch",
            cost_micros=1000,
        )
        self.assertIsNone(event.batch)


class UsageEventCardSnapshotTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="T", products=["metering"])
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")

    def test_snapshot_fields_default_empty(self):
        event = UsageEvent.objects.create(
            tenant=self.tenant, customer=self.customer,
            request_id="r1", idempotency_key="k1", cost_micros=0,
        )
        self.assertEqual(event.card_slug, "")
        self.assertEqual(event.card_name, "")

    def test_snapshot_fields_persisted(self):
        event = UsageEvent.objects.create(
            tenant=self.tenant, customer=self.customer,
            request_id="r1", idempotency_key="k1", cost_micros=0,
            card_slug="gpt_4o", card_name="GPT-4o",
        )
        event.refresh_from_db()
        self.assertEqual(event.card_slug, "gpt_4o")
        self.assertEqual(event.card_name, "GPT-4o")
