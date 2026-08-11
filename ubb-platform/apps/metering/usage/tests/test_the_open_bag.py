"""The one open bag on a posting: what it is, and what it is not (#273).

Was `test_tags.py`, the second bag's own module. The second bag folded into
this one and the tests came with it — the *storage* changed, so every case
below is re-pointed rather than rewritten, and the two cases that only existed
to enforce the retired bag's key shape are gone with the rule (see the module
note in `services/usage_service.py` for why a lowercase-snake key pattern is a
grouping rule wearing a validation hat, and what changes for a caller).
"""

import json
from unittest.mock import patch
from django.test import TestCase, Client, skipUnlessDBFeature
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.metering.usage.models import Posting
from apps.metering.usage.services.usage_service import UsageService


class TheBagIsStoredAsAuthoredTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test"
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1"
        )

    @patch("apps.platform.events.tasks.process_single_event")
    def test_the_bag_is_stored_on_the_posting(self, mock_process):
        result = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_gk1",
            idempotency_key="idem_gk1",
            provider_cost_micros=1_000_000,
            metadata={"department": "sales", "workflow_run": "wf_123"},
        )
        event = Posting.objects.get(id=result["event_id"])
        self.assertEqual(event.metadata,
                         {"department": "sales", "workflow_run": "wf_123"})

    @patch("apps.platform.events.tasks.process_single_event")
    def test_an_absent_bag_is_empty_rather_than_null(self, mock_process):
        """The survivor's own shape, and the one place the fold is visible.

        The retired bag defaulted to NULL, this one to `{}`. Both mean "the
        caller sent no labels"; only one of them can be filtered without a
        null guard at every call site, which is why the survivor's shape is
        the one that survived.
        """
        result = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_gk2",
            idempotency_key="idem_gk2",
            provider_cost_micros=1_000_000,
        )
        event = Posting.objects.get(id=result["event_id"])
        self.assertEqual(event.metadata, {})

    @patch("apps.platform.events.tasks.process_single_event")
    def test_the_tenants_own_keys_are_not_reshaped(self, mock_process):
        """UBB NEVER REWORDS A KEY THE TENANT AUTHORED.

        Mixed case, hyphens, spaces, a single character, and a non-string
        value: every one of these the retired bag refused, and every one of
        them comes back exactly as it was written. The rule this pins is the
        backend half of "a tenant's own identifiers are rendered as they wrote
        them"; the console half is its own ticket, and neither half may
        title-case a key into English nobody chose.
        """
        authored = {"Department": "Sales", "workflow-run": "WF_123",
                    "x": "y", "cost centre": "EMEA", "retries": 3}
        result = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_gk7",
            idempotency_key="idem_gk7",
            provider_cost_micros=1_000_000,
            metadata=authored,
        )
        event = Posting.objects.get(id=result["event_id"])
        self.assertEqual(event.metadata, authored)

    @patch("apps.platform.events.tasks.process_single_event")
    def test_the_retired_bags_key_shape_is_no_longer_enforced(self,
                                                              mock_process):
        """The stated consequence of the fold, pinned rather than discovered.

        `{"Invalid-Key": ...}` and a fifty-first key were both a `ValueError`
        — a 422 on the wire — while the retired bag existed to make chartable
        tokens. The survivor is never charted, so neither rule has anything
        left to protect and a caller that used to be refused is now recorded.
        Nothing is mis-metered: this bag is filtered and read, never priced
        and never grouped.
        """
        result = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_gk8",
            idempotency_key="idem_gk8",
            provider_cost_micros=1_000_000,
            metadata={f"key_{i}": f"val_{i}" for i in range(51)}
                     | {"Invalid-Key": "value"},
        )
        event = Posting.objects.get(id=result["event_id"])
        self.assertEqual(len(event.metadata), 52)


class TheBagIsFilterableTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.tenant = Tenant.objects.create(
            name="Test Tenant", products=["metering", "billing"]
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust_gk"
        )

    @patch("apps.platform.events.tasks.process_single_event")
    def test_the_bag_round_trips_through_the_recording_route(self, mock_process):
        response = self.client.post(
            "/api/v1/metering/usage",
            data=json.dumps({
                "customer_id": str(self.customer.id),
                "request_id": "req_gk_ep1",
                "idempotency_key": "idem_gk_ep1",
                "provider_cost_micros": 1_000_000,
                "metadata": {"department": "engineering"},
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        event = Posting.objects.get(idempotency_key="idem_gk_ep1")
        self.assertEqual(event.metadata, {"department": "engineering"})

    @skipUnlessDBFeature("supports_json_field_contains")
    @patch("apps.platform.events.tasks.process_single_event")
    def test_the_bag_filters_the_usage_list(self, mock_process):
        """FILTERING IS WHAT SURVIVED THE FOLD.

        The query parameters keep the analytics spelling they are published
        under — that vocabulary is slice 7's to migrate — and they now read
        the surviving bag.
        """
        for i, dept in enumerate(["sales", "engineering", "sales"]):
            self.client.post(
                "/api/v1/metering/usage",
                data=json.dumps({
                    "customer_id": str(self.customer.id),
                    "request_id": f"req_filter_{i}",
                    "idempotency_key": f"idem_filter_{i}",
                    "provider_cost_micros": 1_000_000,
                    "metadata": {"department": dept},
                }),
                content_type="application/json",
                HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
            )

        response = self.client.get(
            f"/api/v1/metering/customers/{self.customer.id}/usage"
            "?tag_key=department&tag_value=sales",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["data"]), 2)

    @patch("apps.platform.events.tasks.process_single_event")
    def test_the_bag_is_readable_on_the_detail_response(self, mock_process):
        """READABLE, the other half of what the bag is for."""
        self.client.post(
            "/api/v1/metering/usage",
            data=json.dumps({
                "customer_id": str(self.customer.id),
                "request_id": "req_gk_ep2",
                "idempotency_key": "idem_gk_ep2",
                "provider_cost_micros": 1_000_000,
                "metadata": {"Cost Centre": "EMEA"},
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        event = Posting.objects.get(idempotency_key="idem_gk_ep2")
        detail = self.client.get(
            f"/api/v1/metering/usage/{event.id}",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(detail.status_code, 200)
        # As authored, on the wire, not only in the column.
        self.assertEqual(detail.json()["metadata"], {"Cost Centre": "EMEA"})
