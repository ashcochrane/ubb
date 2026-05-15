import json
import uuid as _uuid

import pytest
from django.test import Client

from apps.metering.pricing.models import Card, Rate
from apps.metering.usage.models import UsageEvent, EventBatch
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant, TenantApiKey


def _create_event(tenant, customer, card=None, group=None, billed=1000, provider_cost=800):
    return UsageEvent.objects.create(
        tenant=tenant,
        customer=customer,
        request_id=f"req_{_uuid.uuid4().hex[:8]}",
        idempotency_key=f"idem_{_uuid.uuid4().hex[:8]}",
        cost_micros=billed,
        provider=card.provider if card else "",
        provider_cost_micros=provider_cost,
        billed_cost_micros=billed,
        card=card,
        group=group,
        usage_metrics={"tokens": 100},
    )


@pytest.mark.django_db
class TestEventFilterOptions:
    def setup_method(self):
        self.tenant = Tenant.objects.create(name="Test", products=["metering"])
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.client = Client()

    def test_filter_options_empty(self):
        resp = self.client.get(
            "/api/v1/platform/events/filter-options",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["customers"] == []
        assert data["groups"] == []
        assert data["cards"] == []
        assert data["ungroupedCount"] == 0
        assert data["cardDimensions"] == {}
        assert data["dimensionPrices"] == {}

    def test_filter_options_with_data(self):
        customer = Customer.objects.create(tenant=self.tenant, external_id="acme")
        card = Card.objects.create(
            tenant=self.tenant, name="Card A", slug="card_a",
            provider="test",
        )
        _create_event(self.tenant, customer, card=card, group="research")
        _create_event(self.tenant, customer, group=None)

        resp = self.client.get(
            "/api/v1/platform/events/filter-options",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        data = resp.json()
        assert len(data["customers"]) == 1
        assert data["customers"][0]["key"] == "acme"
        assert data["customers"][0]["eventCount"] == 2
        assert len(data["groups"]) == 1
        assert data["groups"][0]["key"] == "research"
        assert len(data["cards"]) == 1
        assert data["cards"][0]["key"] == "card_a"
        assert data["ungroupedCount"] == 1

    def test_filter_options_with_card_dimensions(self):
        card = Card.objects.create(
            tenant=self.tenant, name="Card", slug="card_a",
            provider="test",
        )
        Rate.objects.create(
            card=card, metric_name="input_tokens",
            cost_per_unit_micros=100, unit_quantity=1000000,
        )
        resp = self.client.get(
            "/api/v1/platform/events/filter-options",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        data = resp.json()
        assert "card_a" in data["cardDimensions"]
        assert "input_tokens" in data["cardDimensions"]["card_a"]
        assert "input_tokens" in data["dimensionPrices"]
        assert data["dimensionPrices"]["input_tokens"]["costPerUnitMicros"] == 100


@pytest.mark.django_db
class TestEventsList:
    def setup_method(self):
        self.tenant = Tenant.objects.create(name="Test", products=["metering"])
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="acme")
        self.card = Card.objects.create(
            tenant=self.tenant, name="Card", slug="test_card",
            provider="test",
        )
        self.client = Client()

    def test_list_events_empty(self):
        resp = self.client.post(
            "/api/v1/platform/events/list",
            data=json.dumps({}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["events"] == []
        assert data["totalCount"] == 0
        assert data["totalCostMicros"] == 0

    def test_list_events_with_data(self):
        _create_event(self.tenant, self.customer, card=self.card, group="research")

        resp = self.client.post(
            "/api/v1/platform/events/list",
            data=json.dumps({}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["events"]) == 1
        assert data["events"][0]["cardSlug"] == "test_card"
        assert data["events"][0]["customerExternalId"] == "acme"
        assert data["events"][0]["group"] == "research"
        assert data["totalCount"] == 1
        assert data["totalCostMicros"] == 1000

    def test_list_events_filter_by_card_slug(self):
        card2 = Card.objects.create(
            tenant=self.tenant, name="Card2", slug="other_card",
            provider="other",
        )
        _create_event(self.tenant, self.customer, card=self.card)
        _create_event(self.tenant, self.customer, card=card2)

        resp = self.client.post(
            "/api/v1/platform/events/list",
            data=json.dumps({"card_slug": "test_card"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        data = resp.json()
        assert len(data["events"]) == 1
        assert data["events"][0]["cardSlug"] == "test_card"

    def test_list_events_filter_by_group(self):
        _create_event(self.tenant, self.customer, group="research")
        _create_event(self.tenant, self.customer, group="production")

        resp = self.client.post(
            "/api/v1/platform/events/list",
            data=json.dumps({"group": "research"}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        data = resp.json()
        assert len(data["events"]) == 1
        assert data["events"][0]["group"] == "research"


@pytest.mark.django_db
class TestEventsPush:
    def setup_method(self):
        self.tenant = Tenant.objects.create(name="Test", products=["metering"])
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="acme")
        self.card = Card.objects.create(
            tenant=self.tenant, name="Gemini Flash", slug="gemini_flash",
            provider="google",
        )
        Rate.objects.create(
            card=self.card, metric_name="input_tokens",
            pricing_type="per_unit", cost_per_unit_micros=75_000,
            unit_quantity=1_000_000,
        )
        self.client = Client()

    def test_push_events(self):
        resp = self.client.post(
            "/api/v1/platform/events/push",
            data=json.dumps({
                "events": [{
                    "customer_external_id": "acme",
                    "pricing_card": "gemini_flash",
                    "group": "research",
                    "usage_metrics": {"input_tokens": 1000},
                }],
                "reason": "Monthly import",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["pushedCount"] == 1
        assert data["batchId"]
        assert UsageEvent.objects.filter(tenant=self.tenant).count() == 1
        # Verify the event is linked to the batch
        event = UsageEvent.objects.filter(tenant=self.tenant).first()
        assert event.batch_id is not None

    def test_push_events_skips_unknown_customer(self):
        resp = self.client.post(
            "/api/v1/platform/events/push",
            data=json.dumps({
                "events": [{
                    "customer_external_id": "nonexistent",
                    "pricing_card": "gemini_flash",
                    "usage_metrics": {"input_tokens": 1000},
                }],
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["pushedCount"] == 0

    def test_push_events_creates_batch(self):
        self.client.post(
            "/api/v1/platform/events/push",
            data=json.dumps({
                "events": [{
                    "customer_external_id": "acme",
                    "pricing_card": "gemini_flash",
                    "usage_metrics": {"input_tokens": 500},
                }],
                "reason": "Test batch",
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        batch = EventBatch.objects.filter(tenant=self.tenant).first()
        assert batch is not None
        assert batch.action == "added"
        assert batch.reason == "Test batch"
        assert batch.row_count == 1


@pytest.mark.django_db
class TestAuditTrail:
    def setup_method(self):
        self.tenant = Tenant.objects.create(name="Test", products=["metering"])
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.client = Client()

    def test_audit_trail_empty(self):
        resp = self.client.get(
            "/api/v1/platform/events/audit-trail",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_audit_trail_with_batch(self):
        EventBatch.objects.create(
            tenant=self.tenant, action="added",
            reason="Test", row_count=5, author="admin",
        )
        resp = self.client.get(
            "/api/v1/platform/events/audit-trail",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["action"] == "added"
        assert data[0]["rowCount"] == 5


@pytest.mark.django_db
class TestReverseAuditEntry:
    def setup_method(self):
        self.tenant = Tenant.objects.create(name="Test", products=["metering"])
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="acme")
        self.client = Client()

    def test_reverse_batch(self):
        batch = EventBatch.objects.create(
            tenant=self.tenant, action="added",
            reason="Test batch", row_count=1, author="admin",
        )
        event = _create_event(self.tenant, self.customer)
        UsageEvent.objects.filter(id=event.id).update(batch=batch)

        resp = self.client.post(
            f"/api/v1/platform/events/audit-trail/{batch.id}/reverse",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "reversed"

        batch.refresh_from_db()
        assert batch.reversed_at is not None

        from apps.metering.usage.models import Refund
        assert Refund.objects.filter(usage_event=event).exists()

    def test_reverse_already_reversed(self):
        from django.utils import timezone as tz
        batch = EventBatch.objects.create(
            tenant=self.tenant, action="added",
            reason="Test", row_count=0, author="admin",
            reversed_at=tz.now(),
        )
        resp = self.client.post(
            f"/api/v1/platform/events/audit-trail/{batch.id}/reverse",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        assert resp.status_code == 400


@pytest.mark.django_db
class TestEventOutSnapshotFields:
    def setup_method(self):
        self.tenant = Tenant.objects.create(name="T", products=["metering"])
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.client = Client()

        card = Card.objects.create(
            tenant=self.tenant, name="GPT-4o", slug="gpt_4o",
            provider="openai", status="active",
        )
        Rate.objects.create(
            card=card, metric_name="input_tokens",
            cost_per_unit_micros=3_000, provider_cost_per_unit_micros=2_500,
            unit_quantity=1_000_000,
        )
        from apps.metering.usage.services.usage_service import UsageService
        UsageService.record_usage(
            tenant=self.tenant, customer=self.customer,
            request_id="r1", idempotency_key="k1",
            pricing_card="gpt_4o", usage_metrics={"input_tokens": 1_000_000},
        )

    def test_event_list_includes_card_snapshot(self):
        resp = self.client.post(
            "/api/v1/platform/events/list", data=json.dumps({}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["events"]) == 1
        event = body["events"][0]
        assert event["cardSlug"] == "gpt_4o"
        assert event["cardName"] == "GPT-4o"
        assert event["provider"] == "openai"
        assert "eventType" not in event


@pytest.mark.django_db
class TestExportEvents:
    def setup_method(self):
        self.tenant = Tenant.objects.create(name="Test", products=["metering"])
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="acme")
        self.client = Client()

    def test_export_returns_csv(self):
        resp = self.client.post(
            "/api/v1/platform/events/export",
            data=json.dumps({}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        assert resp.status_code == 200
        assert "text/csv" in resp["Content-Type"]
        assert "events_export.csv" in resp["Content-Disposition"]

    def test_export_includes_data(self):
        card = Card.objects.create(
            tenant=self.tenant, name="Card", slug="test_card",
            provider="test",
        )
        _create_event(self.tenant, self.customer, card=card, group="research")

        resp = self.client.post(
            "/api/v1/platform/events/export",
            data=json.dumps({}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "acme" in content
        assert "test_card" in content
        assert "research" in content
