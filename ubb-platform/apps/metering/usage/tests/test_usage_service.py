from unittest.mock import patch, MagicMock
from django.test import TestCase
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.platform.runs.models import Run
from apps.platform.runs.services import RunService, HardStopExceeded, RunNotActive
from apps.metering.pricing.models import Card, Rate, TenantMarkup
from apps.metering.usage.models import UsageEvent
from apps.billing.wallets.models import Wallet
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
        self.wallet = Wallet.objects.create(customer=self.customer)

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
        self.wallet.balance_micros = 100_000_000
        self.wallet.save()

        UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_1",
            idempotency_key="idem_1",
            cost_micros=1_000_000,
        )
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, 100_000_000)

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
        self.wallet.balance_micros = 0
        self.wallet.save()
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
        from apps.billing.topups.models import AutoTopUpConfig, TopUpAttempt

        self.wallet.balance_micros = 0
        self.wallet.save()
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
        self.wallet = Wallet.objects.create(customer=self.customer)

        card = Card.objects.create(
            tenant=self.tenant,
            name="Gemini Flash",
            provider="google_gemini",
            event_type="gemini_api_call",
            dimensions={"model": "gemini-2.0-flash"},
        )
        Rate.objects.create(
            card=card,
            metric_name="input_tokens",
            cost_per_unit_micros=75_000,
            unit_quantity=1_000_000,
        )
        Rate.objects.create(
            card=card,
            metric_name="output_tokens",
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
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, 0)

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_with_raw_metrics_and_margin(self, mock_process):
        from decimal import Decimal

        TenantMarkup.objects.create(
            tenant=self.tenant,
            event_type="gemini_api_call",
            provider="google_gemini",
            margin_pct=20,
        )
        result = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_margin_1",
            idempotency_key="idem_margin_1",
            event_type="gemini_api_call",
            provider="google_gemini",
            usage_metrics={"input_tokens": 1_000_000},
            properties={"model": "gemini-2.0-flash"},
        )
        self.assertEqual(result["provider_cost_micros"], 75_000)
        # margin 20%: 75_000 / (1 - 0.20) = 75_000 / 0.80 = 93_750
        expected_billed = int(Decimal("75000") / Decimal("0.80"))
        self.assertEqual(result["billed_cost_micros"], expected_billed)

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

        card = Card.objects.create(
            tenant=self.tenant,
            name="Gemini Flash",
            provider="google_gemini",
            event_type="gemini_api_call",
            dimensions={"model": "gemini-2.0-flash"},
        )
        Rate.objects.create(
            card=card,
            metric_name="input_tokens",
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


class UsageServiceRunTest(TestCase):
    """Tests for run-aware usage recording (hard stop integration)."""

    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test",
            stripe_connected_account_id="acct_test",
            run_cost_limit_micros=10_000_000,
            hard_stop_balance_micros=-5_000_000,
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1"
        )

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_with_run_accumulates_cost(self, mock_process):
        run = RunService.create_run(
            self.tenant, self.customer, balance_snapshot_micros=20_000_000
        )
        result = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_run_1",
            idempotency_key="idem_run_1",
            cost_micros=3_000_000,
            run_id=run.id,
        )
        self.assertEqual(result["run_total_cost_micros"], 3_000_000)
        self.assertFalse(result["hard_stop"])
        self.assertEqual(result["run_id"], str(run.id))

        # Verify run was updated
        run.refresh_from_db()
        self.assertEqual(run.total_cost_micros, 3_000_000)
        self.assertEqual(run.event_count, 1)

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_with_run_links_event(self, mock_process):
        run = RunService.create_run(
            self.tenant, self.customer, balance_snapshot_micros=20_000_000
        )
        result = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_run_link",
            idempotency_key="idem_run_link",
            cost_micros=1_000_000,
            run_id=run.id,
        )
        event = UsageEvent.objects.get(id=result["event_id"])
        self.assertEqual(event.run_id, run.id)

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_without_run_unchanged(self, mock_process):
        result = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_no_run",
            idempotency_key="idem_no_run",
            cost_micros=1_000_000,
        )
        self.assertIsNone(result["run_total_cost_micros"])
        self.assertFalse(result["hard_stop"])
        self.assertIsNone(result["run_id"])

        event = UsageEvent.objects.get(id=result["event_id"])
        self.assertIsNone(event.run_id)

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_hard_stop_raises_no_event_created(self, mock_process):
        run = RunService.create_run(
            self.tenant, self.customer, balance_snapshot_micros=20_000_000
        )
        # Accumulate close to limit
        UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_hs_1",
            idempotency_key="idem_hs_1",
            cost_micros=9_000_000,
            run_id=run.id,
        )

        # Next event should breach the 10M ceiling
        with self.assertRaises(HardStopExceeded) as ctx:
            UsageService.record_usage(
                tenant=self.tenant,
                customer=self.customer,
                request_id="req_hs_2",
                idempotency_key="idem_hs_2",
                cost_micros=2_000_000,
                run_id=run.id,
            )
        self.assertEqual(ctx.exception.reason, "cost_limit_exceeded")

        # No second event created (transaction rolled back)
        self.assertEqual(
            UsageEvent.objects.filter(tenant=self.tenant, customer=self.customer).count(),
            1,
        )

        # Run total NOT incremented (transaction rolled back)
        run.refresh_from_db()
        self.assertEqual(run.total_cost_micros, 9_000_000)
        self.assertEqual(run.event_count, 1)

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_hard_stop_balance_floor(self, mock_process):
        # balance=3M, hard_stop_balance=-5M → can spend up to 8M
        run = RunService.create_run(
            self.tenant, self.customer, balance_snapshot_micros=3_000_000
        )
        UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_floor_1",
            idempotency_key="idem_floor_1",
            cost_micros=7_000_000,
            run_id=run.id,
        )

        with self.assertRaises(HardStopExceeded) as ctx:
            UsageService.record_usage(
                tenant=self.tenant,
                customer=self.customer,
                request_id="req_floor_2",
                idempotency_key="idem_floor_2",
                cost_micros=2_000_000,
                run_id=run.id,
            )
        self.assertEqual(ctx.exception.reason, "balance_floor_exceeded")

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_outbox_includes_run_id(self, mock_process):
        from apps.platform.events.models import OutboxEvent

        run = RunService.create_run(
            self.tenant, self.customer, balance_snapshot_micros=20_000_000
        )
        UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_outbox_run",
            idempotency_key="idem_outbox_run",
            cost_micros=1_000_000,
            run_id=run.id,
        )
        outbox = OutboxEvent.objects.filter(event_type="usage.recorded").first()
        self.assertEqual(outbox.payload["run_id"], str(run.id))

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_outbox_null_run_id_without_run(self, mock_process):
        from apps.platform.events.models import OutboxEvent

        UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_outbox_norun",
            idempotency_key="idem_outbox_norun",
            cost_micros=1_000_000,
        )
        outbox = OutboxEvent.objects.filter(event_type="usage.recorded").first()
        self.assertIsNone(outbox.payload["run_id"])

    @patch("apps.platform.events.tasks.process_single_event")
    def test_idempotent_response_includes_run_id(self, mock_process):
        """Idempotent replay includes run_id from the original event."""
        run = RunService.create_run(
            self.tenant, self.customer, balance_snapshot_micros=20_000_000
        )
        result1 = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_idem_run",
            idempotency_key="idem_idem_run",
            cost_micros=1_000_000,
            run_id=run.id,
        )
        self.assertEqual(result1["run_id"], str(run.id))

        # Idempotent replay
        result2 = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_idem_run",
            idempotency_key="idem_idem_run",
            cost_micros=1_000_000,
            run_id=run.id,
        )
        self.assertEqual(result2["event_id"], result1["event_id"])
        self.assertEqual(result2["run_id"], str(run.id))
        self.assertFalse(result2["hard_stop"])

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_run_not_active_raises(self, mock_process):
        run = RunService.create_run(
            self.tenant, self.customer, balance_snapshot_micros=20_000_000
        )
        RunService.kill_run(run.id)

        with self.assertRaises(RunNotActive):
            UsageService.record_usage(
                tenant=self.tenant,
                customer=self.customer,
                request_id="req_killed",
                idempotency_key="idem_killed",
                cost_micros=1_000_000,
                run_id=run.id,
            )
