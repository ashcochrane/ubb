import pytest
from django.test import Client

from apps.metering.usage.models import Posting
from apps.platform.event_types.tests._helpers import (
    declares_a_caller_supplied_cost)
from apps.platform.grouping_fields.models import GroupingField
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.platform.work.models import Task


@pytest.mark.django_db
class TestUsageDimensions:
    def setup_method(self):
        # products=[...] is REQUIRED — these routes are gated by _product_check.
        self.tenant = Tenant.objects.create(name="T", products=["metering"])
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        self.client = Client()
        # Every body below states the supplier's own cost, which is admissible
        # only where the Event Type declares that it arrives on the call
        # (#324). Declared here rather than dropped from the bodies: the
        # amounts are incidental to what this module asserts, but a recording
        # call with no cost at all is not the shape these fixtures exercise.
        declares_a_caller_supplied_cost(self.tenant, "completion")

    def _api_headers(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def _declare(self):
        GroupingField.objects.create(tenant=self.tenant, key="model", slot="grouping_field_2",
                                    scope="event", max_cardinality=2)
        GroupingField.objects.create(tenant=self.tenant, key="region", slot="grouping_field_1",
                                    scope="task")

    def _post(self, **extra):
        body = {"customer_id": str(self.customer.id),
                "idempotency_key": "k1", "provider": "openai",
                "event_type": "completion", "provider_cost_micros": 1000}
        body.update(extra)
        return self.client.post("/api/v1/metering/usage", data=body,
                                content_type="application/json", **self._api_headers())

    def test_declared_event_dimension_lands_in_its_slot(self):
        self._declare()
        r = self._post(dimensions={"model": "gpt-4"})
        assert r.status_code == 200
        assert Posting.objects.get(id=r.json()["event_id"]).grouping_field_2 == "gpt-4"

    def test_unknown_grouping_field_is_422(self):
        self._declare()
        r = self._post(dimensions={"nope": "x"})
        assert r.status_code == 422
        assert "unknown grouping field" in r.json()["detail"]

    def test_task_scoped_grouping_field_rejected_on_an_event(self):
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
            data={"customer_id": str(self.customer.id),
                  "idempotency_key": "k9", "provider": "openai",
                  "event_type": "completion", "provider_cost_micros": 1,
                  "dimensions": {"model": "c"}},
            content_type="application/json", **self._api_headers())
        assert r.status_code == 422
        assert "cardinality" in r.json()["detail"]

    def test_the_open_bag_no_longer_becomes_dimensions(self):
        """The reserved-label lifting at usage_service.py (dim1/dim2/dim3 from
        ["product"]/["service"]/["agent"]) is deleted: the open bag is
        free-form labelling only (design 'What this deletes')."""
        self._declare()
        r = self._post(metadata={"service": "extract", "agent": "textract-v2"})
        assert r.status_code == 200
        e = Posting.objects.get(id=r.json()["event_id"])
        assert e.grouping_field_1 == "" and e.grouping_field_2 == ""
        # ...and reserved-NAMED keys still reach storage unchanged. Nothing
        # else asserts this: `test_the_open_bag.py` only covers non-reserved
        # keys.
        assert e.metadata == {"service": "extract", "agent": "textract-v2"}

    # --- What comes BACK: the values keyed by the tenant's own key (#277) ---
    #
    # These live here, beside the write path, for two reasons. The round trip is
    # one claim and reads better as one file; and a new file could not spell the
    # request fields these need without pushing two other slices' recorded
    # extents wider, which the sweep refuses. The absence half of ticket 20 —
    # that no schema anywhere names a physical slot — is its own file,
    # `test_grouping_values_on_the_contract.py`.

    def _detail(self, event_id):
        return self.client.get(f"/api/v1/metering/usage/{event_id}",
                               **self._api_headers())

    def test_the_detail_response_keys_the_values_by_the_declared_key(self):
        self._declare()
        r = self._post(dimensions={"model": "gpt-4"})
        body = self._detail(r.json()["event_id"]).json()
        assert body["grouping_fields"] == {"model": "gpt-4"}

    def test_the_record_response_carries_the_same_object(self):
        """Both posting responses, one shape. They disagreed before this
        ticket: the detail response published the first three slots and the
        record response published the second and third — a pair no reader could
        have predicted and no argument ever chose."""
        self._declare()
        r = self._post(dimensions={"model": "gpt-4"})
        assert r.json()["grouping_fields"] == {"model": "gpt-4"}

    def test_the_object_reaches_the_tenth_slot(self):
        """The old per-slot properties stopped at three, so seven of the ten
        slots #276 built were unreadable through the API. The object reaches
        every one of them, and reaches the next one without a contract
        change."""
        GroupingField.objects.create(tenant=self.tenant, key="tier",
                                     slot="grouping_field_10", scope="event")
        r = self._post(dimensions={"tier": "enterprise"})
        assert r.json()["grouping_fields"] == {"tier": "enterprise"}

    def test_the_record_response_shows_what_the_posting_inherited(self):
        """A task-scoped value is set at the start gate and never sent with the
        event (D6), so the record response is where a caller learns what its
        posting was attributed to WITHOUT a second call. The old per-slot pair
        could show that only when the value happened to land in slot two or
        three."""
        self._declare()
        task = Task.objects.create(tenant=self.tenant, customer=self.customer,
                                   balance_snapshot_micros=0,
                                   grouping_field_1="eu-west-1")
        r = self._post(task_id=str(task.id), dimensions={"model": "gpt-4"})
        assert r.status_code == 200
        assert r.json()["grouping_fields"] == {"region": "eu-west-1",
                                               "model": "gpt-4"}

    def test_an_unset_slot_is_omitted_rather_than_carried_as_empty(self):
        """A declared field the posting never carried is absent from the
        object, not present as "". Publishing the empty string would ask an
        integrator to tell a real value from a placeholder by comparing against
        it — and it would put UBB's "not set" sentinel on the contract."""
        self._declare()
        GroupingField.objects.create(tenant=self.tenant, key="unused",
                                     slot="grouping_field_3", scope="event")
        r = self._post(dimensions={"model": "gpt-4"})
        assert r.json()["grouping_fields"] == {"model": "gpt-4"}

    def test_a_posting_with_no_grouping_values_carries_an_empty_object(self):
        """Empty, never absent and never null: the property is always there and
        always an object, so no reader ever branches on its presence."""
        self._declare()
        r = self._post()
        assert r.json()["grouping_fields"] == {}
        assert self._detail(r.json()["event_id"]).json()["grouping_fields"] == {}

    def test_what_was_sent_is_what_comes_back(self):
        """AC 3 — the read object is the shape the write side already takes, so
        the round trip needs no translation table on either side of it."""
        self._declare()
        sent = {"model": "gpt-4"}
        r = self._post(dimensions=sent)
        assert r.json()["grouping_fields"] == sent
        assert self._detail(r.json()["event_id"]).json()["grouping_fields"] == sent

    def test_neither_response_carries_a_slot_named_property(self):
        self._declare()
        r = self._post(dimensions={"model": "gpt-4"})
        for body in (r.json(), self._detail(r.json()["event_id"]).json()):
            assert not [k for k in body if k.startswith(("dim", "grouping_field_"))
                        and k != "grouping_fields"], body

    def test_product_id_is_gone_from_the_wire_contract(self):
        """Final-fixes wave, Critical 1+2: the legacy `product_id` field is
        deleted from RecordUsageRequest entirely — it broke accept/settle
        price parity (the accept-time estimator never folded it) and bypassed
        the grouping field cardinality cap (no admit, no declaration required).
        django-ninja/pydantic silently ignores an undeclared field by default
        (Schema.model_config sets no `extra` override), so a caller still
        sending `product_id` gets a normal 200 with dim1 untouched — NOT a
        422 — and dim1 comes only from a declared `dimensions` value."""
        self._declare()
        r = self._post(product_id="search")
        assert r.status_code == 200
        e = Posting.objects.get(id=r.json()["event_id"])
        assert e.grouping_field_1 == ""
