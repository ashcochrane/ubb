import json
from django.db import connection
from django.test import TestCase, Client, skipUnlessDBFeature
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.usage.models import UsageEvent
from apps.usage.services.usage_service import UsageService


class GroupKeysValidationTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test"
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1"
        )
        self.customer.wallet.balance_micros = 100_000_000
        self.customer.wallet.save()

    def test_group_keys_stored_on_event(self):
        result = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_gk1",
            idempotency_key="idem_gk1",
            cost_micros=1_000_000,
            group_keys={"department": "sales", "workflow_run": "wf_123"},
        )
        event = UsageEvent.objects.get(id=result["event_id"])
        self.assertEqual(event.group_keys, {"department": "sales", "workflow_run": "wf_123"})

    def test_group_keys_null_by_default(self):
        result = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_gk2",
            idempotency_key="idem_gk2",
            cost_micros=1_000_000,
        )
        event = UsageEvent.objects.get(id=result["event_id"])
        self.assertIsNone(event.group_keys)

    def test_group_keys_max_10_keys(self):
        keys = {f"key_{i}": f"val_{i}" for i in range(11)}
        with self.assertRaises(ValueError):
            UsageService.record_usage(
                tenant=self.tenant,
                customer=self.customer,
                request_id="req_gk3",
                idempotency_key="idem_gk3",
                cost_micros=1_000_000,
                group_keys=keys,
            )

    def test_group_keys_key_format_validation(self):
        with self.assertRaises(ValueError):
            UsageService.record_usage(
                tenant=self.tenant,
                customer=self.customer,
                request_id="req_gk4",
                idempotency_key="idem_gk4",
                cost_micros=1_000_000,
                group_keys={"Invalid-Key": "value"},
            )

    def test_group_keys_single_char_key_rejected(self):
        """Keys must be at least 2 characters."""
        with self.assertRaises(ValueError):
            UsageService.record_usage(
                tenant=self.tenant,
                customer=self.customer,
                request_id="req_gk6",
                idempotency_key="idem_gk6",
                cost_micros=1_000_000,
                group_keys={"x": "value"},
            )

    def test_group_keys_value_must_be_string(self):
        with self.assertRaises(ValueError):
            UsageService.record_usage(
                tenant=self.tenant,
                customer=self.customer,
                request_id="req_gk5",
                idempotency_key="idem_gk5",
                cost_micros=1_000_000,
                group_keys={"key": 123},
            )


class GroupKeysEndpointTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.tenant = Tenant.objects.create(name="Test Tenant")
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust_gk"
        )
        self.customer.wallet.balance_micros = 100_000_000
        self.customer.wallet.save()

    def test_record_usage_with_group_keys(self):
        response = self.client.post(
            "/api/v1/usage",
            data=json.dumps({
                "customer_id": str(self.customer.id),
                "request_id": "req_gk_ep1",
                "idempotency_key": "idem_gk_ep1",
                "cost_micros": 1_000_000,
                "group_keys": {"department": "engineering"},
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        event = UsageEvent.objects.get(idempotency_key="idem_gk_ep1")
        self.assertEqual(event.group_keys, {"department": "engineering"})

    @skipUnlessDBFeature("supports_json_field_contains")
    def test_usage_filter_by_group_key(self):
        for i, dept in enumerate(["sales", "engineering", "sales"]):
            self.client.post(
                "/api/v1/usage",
                data=json.dumps({
                    "customer_id": str(self.customer.id),
                    "request_id": f"req_filter_{i}",
                    "idempotency_key": f"idem_filter_{i}",
                    "cost_micros": 1_000_000,
                    "group_keys": {"department": dept},
                }),
                content_type="application/json",
                HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
            )

        response = self.client.get(
            f"/api/v1/customers/{self.customer.id}/usage?group_key=department&group_value=sales",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["data"]), 2)
