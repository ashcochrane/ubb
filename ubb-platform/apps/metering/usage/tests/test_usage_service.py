from unittest.mock import patch, MagicMock
from django.test import TestCase
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.metering.pricing.models import ProviderRate, TenantMarkup
from apps.metering.usage.models import UsageEvent
from apps.metering.usage.services.usage_service import UsageService


class UsageServiceCoreTest(TestCase):
    """Tests for the decoupled UsageService.

    After decoupling, UsageService:
    - Records usage events
    - Writes outbox events
    - Does NOT touch the wallet, suspend customers, or trigger auto-topup
    - Always returns new_balance_micros=None, suspended=False
    """
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test"
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1"
        )

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_creates_event(self, mock_process):
        result = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_1",
            idempotency_key="idem_1",
            cost_micros=1_000_000,
        )
        self.assertIsNone(result["new_balance_micros"])
        self.assertFalse(result["suspended"])
        # Verify event was created
        event = UsageEvent.objects.get(id=result["event_id"])
        self.assertEqual(event.cost_micros, 1_000_000)

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_does_not_deduct_wallet(self, mock_process):
        self.customer.wallet.balance_micros = 100_000_000
        self.customer.wallet.save()

        UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_1",
            idempotency_key="idem_1",
            cost_micros=1_000_000,
        )
        self.customer.wallet.refresh_from_db()
        self.assertEqual(self.customer.wallet.balance_micros, 100_000_000)

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_idempotent(self, mock_process):
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
        # Only one event created
        self.assertEqual(
            UsageEvent.objects.filter(
                tenant=self.tenant, customer=self.customer, idempotency_key="idem_2"
            ).count(),
            1,
        )

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_does_not_suspend_on_threshold(self, mock_process):
        """Suspension is now billing's responsibility via outbox handler."""
        self.customer.wallet.balance_micros = 0
        self.customer.wallet.save()
        result = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_3",
            idempotency_key="idem_3",
            cost_micros=10_000_000,
        )
        self.assertFalse(result["suspended"])
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.status, "active")

    @patch("apps.platform.events.tasks.process_single_event")
    def test_idempotent_response_returns_none_balance(self, mock_process):
        """Idempotent replay returns None for new_balance_micros."""
        result1 = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_snap_1",
            idempotency_key="idem_snap_1",
            cost_micros=1_000_000,
        )
        self.assertIsNone(result1["new_balance_micros"])

        result2 = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_snap_1",
            idempotency_key="idem_snap_1",
            cost_micros=1_000_000,
        )
        self.assertEqual(result2["event_id"], result1["event_id"])
        self.assertIsNone(result2["new_balance_micros"])

    @patch("apps.platform.events.tasks.process_single_event")
    def test_auto_topup_not_triggered_by_metering(self, mock_process):
        """Auto-topup is now billing's responsibility via outbox handler."""
        from apps.platform.customers.models import AutoTopUpConfig, TopUpAttempt

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
        # No attempt created by metering -- billing handles this now
        attempt = TopUpAttempt.objects.filter(
            customer=self.customer, trigger="auto_topup", status="pending"
        ).first()
        self.assertIsNone(attempt)


class UsageServicePricingTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test"
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1"
        )

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

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_with_raw_metrics(self, mock_process):
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
        # Wallet NOT deducted (billing handles this now)
        self.customer.wallet.refresh_from_db()
        self.assertEqual(self.customer.wallet.balance_micros, 0)

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_with_raw_metrics_and_markup(self, mock_process):
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

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_legacy_cost_micros_still_works(self, mock_process):
        result = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_legacy_1",
            idempotency_key="idem_legacy_1",
            cost_micros=1_000_000,
        )
        self.assertIsNone(result["provider_cost_micros"])
        self.assertIsNone(result["billed_cost_micros"])
        self.assertIsNone(result["new_balance_micros"])

    @patch("apps.platform.events.tasks.process_single_event")
    def test_raw_metrics_event_stores_provenance(self, mock_process):
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

    @patch("apps.platform.events.tasks.process_single_event")
    def test_raw_metrics_idempotent_includes_dual_costs(self, mock_process):
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


class UsageServiceEventEmissionTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test"
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1"
        )

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_writes_outbox_event(self, mock_process):
        from apps.platform.events.models import OutboxEvent

        result = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_emit_1",
            idempotency_key="idem_emit_1",
            cost_micros=1_000_000,
        )
        outbox = OutboxEvent.objects.get(event_type="usage.recorded")
        self.assertEqual(outbox.payload["tenant_id"], str(self.tenant.id))
        self.assertEqual(outbox.payload["customer_id"], str(self.customer.id))
        self.assertEqual(outbox.payload["cost_micros"], 1_000_000)
        self.assertEqual(outbox.payload["event_type"], "")
        self.assertEqual(outbox.payload["event_id"], result["event_id"])

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_writes_billed_cost_for_priced_events(self, mock_process):
        from apps.platform.events.models import OutboxEvent

        ProviderRate.objects.create(
            provider="google_gemini",
            event_type="gemini_api_call",
            metric_name="input_tokens",
            dimensions={"model": "gemini-2.0-flash"},
            cost_per_unit_micros=75_000,
            unit_quantity=1_000_000,
        )
        result = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_emit_2",
            idempotency_key="idem_emit_2",
            event_type="gemini_api_call",
            provider="google_gemini",
            usage_metrics={"input_tokens": 1_000_000},
            properties={"model": "gemini-2.0-flash"},
        )
        outbox = OutboxEvent.objects.get(event_type="usage.recorded")
        self.assertEqual(outbox.payload["cost_micros"], 75_000)  # billed_cost_micros
        self.assertEqual(outbox.payload["event_type"], "gemini_api_call")
        self.assertEqual(outbox.payload["event_id"], result["event_id"])
