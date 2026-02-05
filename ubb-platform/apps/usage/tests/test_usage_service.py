from unittest.mock import patch
from django.test import TestCase
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer, AutoTopUpConfig, TopUpAttempt
from apps.pricing.models import ProviderRate, TenantMarkup
from apps.usage.models import UsageEvent
from apps.usage.services.usage_service import UsageService


class UsageServiceLockingTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test"
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1"
        )
        # Credit wallet so we can deduct
        self.customer.wallet.balance_micros = 100_000_000
        self.customer.wallet.save()

    def test_record_usage_deducts_wallet(self):
        result = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_1",
            idempotency_key="idem_1",
            cost_micros=1_000_000,
        )
        self.assertEqual(result["new_balance_micros"], 99_000_000)
        self.assertFalse(result["suspended"])

    def test_record_usage_idempotent(self):
        result1 = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_2",
            idempotency_key="idem_2",
            cost_micros=1_000_000,
        )
        result2 = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_2",
            idempotency_key="idem_2",
            cost_micros=1_000_000,
        )
        self.assertEqual(result1["event_id"], result2["event_id"])
        # Balance should only be deducted once
        self.customer.wallet.refresh_from_db()
        self.assertEqual(self.customer.wallet.balance_micros, 99_000_000)

    def test_record_usage_suspends_on_threshold(self):
        self.customer.wallet.balance_micros = 0
        self.customer.wallet.save()
        result = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_3",
            idempotency_key="idem_3",
            cost_micros=10_000_000,  # pushes past threshold
        )
        self.assertTrue(result["suspended"])
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.status, "suspended")

    def test_idempotent_response_returns_original_balance(self):
        """Replay of same idempotency key returns the balance snapshot from original recording."""
        # First usage: 100M -> 99M
        result1 = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_snap_1",
            idempotency_key="idem_snap_1",
            cost_micros=1_000_000,
        )
        self.assertEqual(result1["new_balance_micros"], 99_000_000)

        # Second usage with different key: 99M -> 98M
        result2 = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_snap_2",
            idempotency_key="idem_snap_2",
            cost_micros=1_000_000,
        )
        self.assertEqual(result2["new_balance_micros"], 98_000_000)

        # Replay first idempotency key — should return 99M (original snapshot), not 98M
        result3 = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_snap_1",
            idempotency_key="idem_snap_1",
            cost_micros=1_000_000,
        )
        self.assertEqual(result3["event_id"], result1["event_id"])
        self.assertEqual(result3["new_balance_micros"], 99_000_000)

    def test_auto_topup_attempt_created(self):
        self.customer.wallet.balance_micros = 0
        self.customer.wallet.save()
        AutoTopUpConfig.objects.create(
            customer=self.customer,
            is_enabled=True,
            trigger_threshold_micros=5_000_000,
            top_up_amount_micros=20_000_000,
        )
        UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_4",
            idempotency_key="idem_4",
            cost_micros=1_000_000,
        )
        # Verify the attempt was created
        attempt = TopUpAttempt.objects.filter(
            customer=self.customer, trigger="auto_topup", status="pending"
        ).first()
        self.assertIsNotNone(attempt)


class UsageServicePricingTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test"
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1"
        )
        self.customer.wallet.balance_micros = 100_000_000
        self.customer.wallet.save()

        ProviderRate.objects.create(
            provider="google_gemini",
            event_type="gemini_api_call",
            metric_name="input_tokens",
            dimensions={"model": "gemini-2.0-flash"},
            cost_per_unit_micros=75_000,
            unit_quantity=1_000_000,
        )
        ProviderRate.objects.create(
            provider="google_gemini",
            event_type="gemini_api_call",
            metric_name="output_tokens",
            dimensions={"model": "gemini-2.0-flash"},
            cost_per_unit_micros=300_000,
            unit_quantity=1_000_000,
        )

    def test_record_usage_with_raw_metrics(self):
        result = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_priced_1",
            idempotency_key="idem_priced_1",
            event_type="gemini_api_call",
            provider="google_gemini",
            usage_metrics={"input_tokens": 1_000_000},
            properties={"model": "gemini-2.0-flash"},
        )
        self.assertEqual(result["provider_cost_micros"], 75_000)
        self.assertEqual(result["billed_cost_micros"], 75_000)
        self.customer.wallet.refresh_from_db()
        self.assertEqual(self.customer.wallet.balance_micros, 100_000_000 - 75_000)

    def test_record_usage_with_raw_metrics_and_markup(self):
        TenantMarkup.objects.create(
            tenant=self.tenant,
            event_type="gemini_api_call",
            provider="google_gemini",
            markup_percentage_micros=20_000_000,
        )
        result = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_markup_1",
            idempotency_key="idem_markup_1",
            event_type="gemini_api_call",
            provider="google_gemini",
            usage_metrics={"input_tokens": 1_000_000},
            properties={"model": "gemini-2.0-flash"},
        )
        self.assertEqual(result["provider_cost_micros"], 75_000)
        self.assertEqual(result["billed_cost_micros"], 75_000 + 15_000)

    def test_record_usage_legacy_cost_micros_still_works(self):
        result = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_legacy_1",
            idempotency_key="idem_legacy_1",
            cost_micros=1_000_000,
        )
        self.assertIsNone(result["provider_cost_micros"])
        self.assertIsNone(result["billed_cost_micros"])
        self.assertEqual(result["new_balance_micros"], 99_000_000)

    def test_raw_metrics_event_stores_provenance(self):
        UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_prov_1",
            idempotency_key="idem_prov_1",
            event_type="gemini_api_call",
            provider="google_gemini",
            usage_metrics={"input_tokens": 500},
            properties={"model": "gemini-2.0-flash"},
        )
        event = UsageEvent.objects.get(
            idempotency_key="idem_prov_1", tenant=self.tenant, customer=self.customer
        )
        self.assertEqual(event.event_type, "gemini_api_call")
        self.assertEqual(event.provider, "google_gemini")
        self.assertIn("engine_version", event.pricing_provenance)
        self.assertIn("input_tokens", event.pricing_provenance["metrics"])

    def test_raw_metrics_idempotent_includes_dual_costs(self):
        kwargs = dict(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_idem_priced",
            idempotency_key="idem_idem_priced",
            event_type="gemini_api_call",
            provider="google_gemini",
            usage_metrics={"input_tokens": 1_000_000},
            properties={"model": "gemini-2.0-flash"},
        )
        result1 = UsageService.record_usage(**kwargs)
        result2 = UsageService.record_usage(**kwargs)
        self.assertEqual(result1["event_id"], result2["event_id"])
        self.assertEqual(result2["provider_cost_micros"], 75_000)
        self.assertEqual(result2["billed_cost_micros"], 75_000)
