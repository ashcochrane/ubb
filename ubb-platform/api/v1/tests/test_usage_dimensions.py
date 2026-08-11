import pytest
from django.test import Client

from apps.metering.usage.models import Posting
from apps.platform.grouping_fields.models import GroupingField
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer


@pytest.mark.django_db
class TestUsageDimensions:
    def setup_method(self):
        # products=[...] is REQUIRED — these routes are gated by _product_check.
        self.tenant = Tenant.objects.create(name="T", products=["metering"])
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        self.client = Client()

    def _api_headers(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def _declare(self):
        GroupingField.objects.create(tenant=self.tenant, key="model", slot="dim2",
                                    scope="event", max_cardinality=2)
        GroupingField.objects.create(tenant=self.tenant, key="region", slot="dim1",
                                    scope="task")

    def _post(self, **extra):
        body = {"customer_id": str(self.customer.id), "request_id": "r1",
                "idempotency_key": "k1", "provider": "openai",
                "event_type": "completion", "provider_cost_micros": 1000}
        body.update(extra)
        return self.client.post("/api/v1/metering/usage", data=body,
                                content_type="application/json", **self._api_headers())

    def test_declared_event_dimension_lands_in_its_slot(self):
        self._declare()
        r = self._post(dimensions={"model": "gpt-4"})
        assert r.status_code == 200
        assert Posting.objects.get(id=r.json()["event_id"]).dim2 == "gpt-4"

    def test_unknown_dimension_is_422(self):
        self._declare()
        r = self._post(dimensions={"nope": "x"})
        assert r.status_code == 422
        assert "unknown dimension" in r.json()["detail"]

    def test_task_scoped_dimension_rejected_on_an_event(self):
        self._declare()
        r = self._post(dimensions={"region": "eu"})
        assert r.status_code == 422
        assert "scope" in r.json()["detail"]

    def test_cardinality_overflow_is_422(self):
        self._declare()
        self._post(dimensions={"model": "a"})
        self._post(dimensions={"model": "b"})
        r = self.client.post(
            "/api/v1/metering/usage",
            data={"customer_id": str(self.customer.id), "request_id": "r9",
                  "idempotency_key": "k9", "provider": "openai",
                  "event_type": "completion", "provider_cost_micros": 1,
                  "dimensions": {"model": "c"}},
            content_type="application/json", **self._api_headers())
        assert r.status_code == 422
        assert "cardinality" in r.json()["detail"]

    def test_tags_no_longer_become_dimensions(self):
        """The reserved-tag lifting at usage_service.py (dim1/dim2/dim3 from
        tags["product"]/["service"]/["agent"]) is deleted: tags are free-form
        labels only (design 'What this deletes')."""
        self._declare()
        r = self._post(tags={"service": "extract", "agent": "textract-v2"})
        assert r.status_code == 200
        e = Posting.objects.get(id=r.json()["event_id"])
        assert e.dim1 == "" and e.dim2 == ""
        # ...and reserved-NAMED tags still reach storage unchanged. Nothing else
        # asserts this: test_tags.py only covers non-reserved keys.
        assert e.tags == {"service": "extract", "agent": "textract-v2"}

    def test_product_id_is_gone_from_the_wire_contract(self):
        """Final-fixes wave, Critical 1+2: the legacy `product_id` field is
        deleted from RecordUsageRequest entirely — it broke accept/settle
        price parity (the accept-time estimator never folded it) and bypassed
        the dimension cardinality cap (no admit, no declaration required).
        django-ninja/pydantic silently ignores an undeclared field by default
        (Schema.model_config sets no `extra` override), so a caller still
        sending `product_id` gets a normal 200 with dim1 untouched — NOT a
        422 — and dim1 comes only from a declared `dimensions` value."""
        self._declare()
        r = self._post(product_id="search")
        assert r.status_code == 200
        e = Posting.objects.get(id=r.json()["event_id"])
        assert e.dim1 == ""
