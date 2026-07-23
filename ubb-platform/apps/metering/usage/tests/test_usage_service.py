from unittest.mock import patch, MagicMock
from django.test import TestCase
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.platform.tasks.models import Task
from apps.platform.tasks.services import TaskService
from apps.metering.usage.models import UsageEvent
from apps.billing.wallets.models import Wallet
from apps.metering.usage.services.usage_service import UsageService, _result


# Tier-2 (D5/I4): the customer-wide stop verdict must travel on EVERY
# record_usage return path. P0 only adds the fields (defaulting to the old
# behavior); this guards against the verdict being half-wired in P3 (the
# classic bug is updating the happy path but missing the replay returns).
_STOP_KEYS = {"stop", "stop_reason", "stop_scope"}

# One-rule (#37): the full record_usage result contract. hard_stop and
# run_total_cost_micros are RETIRED; both task totals travel denominationally
# explicit, and parent_task_id names the unit's parent when it is a subtask
# (#38). Kill directives never ride the result at all (#112): the recording
# core registers kill execution on its own transaction.on_commit — the
# exact-key-set assertion below pins that nothing internal can sneak in.
_RESULT_KEYS = {
    "event_id", "provider_cost_micros", "billed_cost_micros", "units",
    "new_balance_micros", "suspended",
    "task_id", "parent_task_id",
    "task_total_billed_cost_micros", "task_total_provider_cost_micros",
    "stop", "stop_reason", "stop_scope", "stop_context",
    "usage_metrics", "pricing_provenance", "service_id", "agent_id",
}


class ResultSignatureTest(TestCase):
    """P0 acceptance gate (D5/I4): stop fields present on all three paths."""

    def setUp(self):
        self.tenant = Tenant.objects.create(name="T")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        Wallet.objects.create(customer=self.customer)

    def test_result_builder_pins_the_one_rule_key_set(self):
        # Both idempotent-replay returns go through this single builder, so
        # asserting it here covers the replay paths that are awkward to
        # trigger deterministically.
        event = MagicMock(
            id="e1", provider_cost_micros=1, billed_cost_micros=1, units=None,
            task_id=None, usage_metrics={}, pricing_provenance={},
            service_id="", agent_id="", stop_context=None,
        )
        out = _result(event)
        # The EXACT new key set — retired keys (hard_stop,
        # run_total_cost_micros, run_id) can never sneak back in.
        self.assertEqual(set(out), _RESULT_KEYS)
        self.assertNotIn("hard_stop", out)
        self.assertFalse(out["stop"])
        self.assertIsNone(out["stop_reason"])
        self.assertIsNone(out["stop_scope"])
        self.assertFalse(out["suspended"])
        self.assertIsNone(out["new_balance_micros"])
        self.assertIsNone(out["parent_task_id"])
        self.assertIsNone(out["task_total_billed_cost_micros"])
        self.assertIsNone(out["task_total_provider_cost_micros"])

    @patch("apps.platform.events.tasks.process_single_event")
    def test_stop_fields_on_happy_path_and_replay(self, _mock):
        first = UsageService.record_usage(
            tenant=self.tenant, customer=self.customer,
            request_id="r1", idempotency_key="k1", provider_cost_micros=1_000_000,
        )
        self.assertTrue(_STOP_KEYS <= set(first), "stop fields missing on happy path")
        self.assertFalse(first["stop"])

        # Same idempotency_key -> the replay return (the path that returns the
        # original event) must ALSO carry the stop fields.
        replay = UsageService.record_usage(
            tenant=self.tenant, customer=self.customer,
            request_id="r1", idempotency_key="k1", provider_cost_micros=1_000_000,
        )
        self.assertEqual(first["event_id"], replay["event_id"])
        self.assertTrue(_STOP_KEYS <= set(replay), "stop fields missing on replay path")
        self.assertFalse(replay["stop"])


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
            provider_cost_micros=1_000_000,
        )
        self.assertIsNone(result["new_balance_micros"])
        self.assertFalse(result["suspended"])
        # Verify event was created
        event = UsageEvent.objects.get(id=result["event_id"])
        self.assertEqual(event.billed_cost_micros, 1_000_000)

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_does_not_deduct_wallet(self, mock_process):
        self.wallet.balance_micros = 100_000_000
        self.wallet.save()

        UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_1",
            idempotency_key="idem_1",
            provider_cost_micros=1_000_000,
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
            provider_cost_micros=1_000_000,
        )
        result2 = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_2",
            idempotency_key="idem_2",
            provider_cost_micros=1_000_000,
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
            provider_cost_micros=10_000_000,
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
            provider_cost_micros=1_000_000,
        )
        self.assertIsNone(result1["new_balance_micros"])

        result2 = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_snap_1",
            idempotency_key="idem_snap_1",
            provider_cost_micros=1_000_000,
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
            provider_cost_micros=1_000_000,
        )
        # No attempt created by metering -- billing handles this now
        attempt = TopUpAttempt.objects.filter(
            customer=self.customer, trigger="auto_topup", status="pending"
        ).first()
        self.assertIsNone(attempt)


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
            provider_cost_micros=1_000_000,
        )
        outbox = OutboxEvent.objects.get(event_type="usage.recorded")
        self.assertEqual(outbox.payload["tenant_id"], str(self.tenant.id))
        self.assertEqual(outbox.payload["customer_id"], str(self.customer.id))
        self.assertEqual(outbox.payload["cost_micros"], 1_000_000)
        self.assertEqual(outbox.payload["event_type"], "")
        self.assertEqual(outbox.payload["event_id"], result["event_id"])

class UsageServiceTaskTest(TestCase):
    """Task-aware usage recording at the SERVICE seam (one-rule #37).

    The service's ONE accumulate primitive never raises on limits: every
    event — including the tipping event and everything after a kill — lands,
    bills, and counts into BOTH totals. Crossing verdicts ride the result's
    stop fields; kill execution registers on the recording transaction's
    on_commit (#112), which never fires inside the test transaction — so the
    task is still active when record_usage returns here.
    """

    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test",
            stripe_connected_account_id="acct_test",
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1"
        )

    def _task(self, balance=20_000_000, limit=None, floor=None):
        return TaskService.create_task(
            self.tenant, self.customer, balance_snapshot_micros=balance,
            provider_cost_limit_micros=limit, floor_snapshot_micros=floor,
            billing_owner_id=self.customer.id,
        )

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_with_task_accumulates_both_totals(self, mock_process):
        task = self._task(balance=20_000_000)
        result = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_task_1",
            idempotency_key="idem_task_1",
            provider_cost_micros=3_000_000,
            task_id=task.id,
        )
        self.assertEqual(result["task_total_billed_cost_micros"], 3_000_000)
        self.assertEqual(result["task_total_provider_cost_micros"], 3_000_000)
        self.assertFalse(result["stop"])
        self.assertEqual(result["task_id"], str(task.id))
        self.assertNotIn("hard_stop", result)

        # Verify task was updated — BOTH totals, denominationally explicit.
        task.refresh_from_db()
        self.assertEqual(task.total_billed_cost_micros, 3_000_000)
        self.assertEqual(task.total_provider_cost_micros, 3_000_000)
        self.assertEqual(task.event_count, 1)

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_with_task_links_event(self, mock_process):
        task = self._task(balance=20_000_000)
        result = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_task_link",
            idempotency_key="idem_task_link",
            provider_cost_micros=1_000_000,
            task_id=task.id,
        )
        event = UsageEvent.objects.get(id=result["event_id"])
        self.assertEqual(event.task_id, task.id)

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_without_task_unchanged(self, mock_process):
        result = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_no_task",
            idempotency_key="idem_no_task",
            provider_cost_micros=1_000_000,
        )
        self.assertIsNone(result["task_total_billed_cost_micros"])
        self.assertIsNone(result["task_total_provider_cost_micros"])
        self.assertFalse(result["stop"])
        self.assertIsNone(result["task_id"])
        self.assertNotIn("hard_stop", result)

        event = UsageEvent.objects.get(id=result["event_id"])
        self.assertIsNone(event.task_id)

    @patch("apps.platform.events.tasks.process_single_event")
    def test_task_limit_crossing_records_event_and_returns_stop(self, mock_process):
        """One-rule: crossing the COGS limit is a VERDICT, never a wall — the
        tipping event lands, bills, and counts; the service seam leaves the
        task active (the kill fires on the recording transaction's commit,
        which the test transaction never reaches)."""
        task = self._task(balance=20_000_000, limit=10_000_000, floor=-5_000_000)
        # Accumulate close to the limit.
        UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_hs_1",
            idempotency_key="idem_hs_1",
            provider_cost_micros=9_000_000,
            task_id=task.id,
        )

        # The next event pushes the PROVIDER total past the 10M ceiling.
        result = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_hs_2",
            idempotency_key="idem_hs_2",
            provider_cost_micros=2_000_000,
            task_id=task.id,
        )
        self.assertTrue(result["stop"])
        self.assertEqual(result["stop_reason"], "task_limit")
        self.assertEqual(result["stop_scope"], "task")

        # The tipping event WAS created and both totals include it.
        self.assertEqual(
            UsageEvent.objects.filter(tenant=self.tenant, customer=self.customer).count(),
            2,
        )
        self.assertEqual(result["task_total_billed_cost_micros"], 11_000_000)
        self.assertEqual(result["task_total_provider_cost_micros"], 11_000_000)
        task.refresh_from_db()
        self.assertEqual(task.total_billed_cost_micros, 11_000_000)
        self.assertEqual(task.total_provider_cost_micros, 11_000_000)
        self.assertEqual(task.event_count, 2)
        # Still ACTIVE at the service seam — the kill fires only at commit.
        self.assertEqual(task.status, "active")

    @patch("apps.platform.events.tasks.process_single_event")
    def test_floor_snapshot_crossing_returns_customer_floor(self, mock_process):
        # balance snapshot 3M, floor -5M -> the estimated balance may fall to
        # -5M; the event that drives it below returns the customer_floor stop.
        task = self._task(balance=3_000_000, limit=10_000_000, floor=-5_000_000)
        UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_floor_1",
            idempotency_key="idem_floor_1",
            provider_cost_micros=7_000_000,
            task_id=task.id,
        )

        result = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_floor_2",
            idempotency_key="idem_floor_2",
            provider_cost_micros=2_000_000,
            task_id=task.id,
        )
        self.assertTrue(result["stop"])
        self.assertEqual(result["stop_reason"], "customer_floor")
        self.assertEqual(result["stop_scope"], "task")
        # Landed and billed; still active at the service seam.
        self.assertEqual(UsageEvent.objects.count(), 2)
        task.refresh_from_db()
        self.assertEqual(task.total_billed_cost_micros, 9_000_000)
        self.assertEqual(task.status, "active")

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_on_killed_task_lands_and_counts(self, mock_process):
        task = self._task(balance=20_000_000)
        TaskService.kill_task(task.id)

        result = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_killed",
            idempotency_key="idem_killed",
            provider_cost_micros=1_000_000,
            task_id=task.id,
        )
        self.assertTrue(result["stop"])
        self.assertEqual(result["stop_reason"], "task_not_active")
        self.assertEqual(result["stop_scope"], "task")

        # The event still landed, billed, and counted into both totals.
        event = UsageEvent.objects.get(id=result["event_id"])
        self.assertEqual(event.task_id, task.id)
        task.refresh_from_db()
        self.assertEqual(task.status, "killed")
        self.assertEqual(task.total_billed_cost_micros, 1_000_000)
        self.assertEqual(task.total_provider_cost_micros, 1_000_000)
        self.assertEqual(task.event_count, 1)

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_outbox_includes_task_id(self, mock_process):
        from apps.platform.events.models import OutboxEvent

        task = self._task(balance=20_000_000)
        UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_outbox_task",
            idempotency_key="idem_outbox_task",
            provider_cost_micros=1_000_000,
            task_id=task.id,
        )
        outbox = OutboxEvent.objects.filter(event_type="usage.recorded").first()
        self.assertEqual(outbox.payload["task_id"], str(task.id))

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_outbox_null_task_id_without_task(self, mock_process):
        from apps.platform.events.models import OutboxEvent

        UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_outbox_notask",
            idempotency_key="idem_outbox_notask",
            provider_cost_micros=1_000_000,
        )
        outbox = OutboxEvent.objects.filter(event_type="usage.recorded").first()
        self.assertIsNone(outbox.payload["task_id"])

    @patch("apps.platform.events.tasks.process_single_event")
    def test_idempotent_replay_returns_task_id_and_none_totals(self, mock_process):
        """Idempotent replay includes task_id from the original event but the
        task totals are None (the replay never re-reads the task row)."""
        task = self._task(balance=20_000_000)
        result1 = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_idem_task",
            idempotency_key="idem_idem_task",
            provider_cost_micros=1_000_000,
            task_id=task.id,
        )
        self.assertEqual(result1["task_id"], str(task.id))

        # Idempotent replay
        result2 = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_idem_task",
            idempotency_key="idem_idem_task",
            provider_cost_micros=1_000_000,
            task_id=task.id,
        )
        self.assertEqual(result2["event_id"], result1["event_id"])
        self.assertEqual(result2["task_id"], str(task.id))
        self.assertIsNone(result2["task_total_billed_cost_micros"])
        self.assertIsNone(result2["task_total_provider_cost_micros"])
        self.assertNotIn("hard_stop", result2)

    @patch("apps.platform.events.tasks.process_single_event")
    def test_concurrent_duplicate_does_not_double_count_task(self, mock_process):
        task = self._task(balance=100_000_000)
        UsageService.record_usage(tenant=self.tenant, customer=self.customer,
            request_id="req_dup", idempotency_key="idem_dup",
            provider_cost_micros=5_000_000, task_id=task.id)
        task.refresh_from_db()
        self.assertEqual(task.total_billed_cost_micros, 5_000_000)
        self.assertEqual(task.total_provider_cost_micros, 5_000_000)
        self.assertEqual(task.event_count, 1)
        orig_filter = UsageEvent.objects.filter
        class _MissingFirst:
            def first(self): return None
        def _fake_filter(*args, **kwargs):
            if "idempotency_key" in kwargs:
                return _MissingFirst()
            return orig_filter(*args, **kwargs)
        with patch.object(UsageEvent.objects, "filter", side_effect=_fake_filter):
            UsageService.record_usage(tenant=self.tenant, customer=self.customer,
                request_id="req_dup", idempotency_key="idem_dup",
                provider_cost_micros=5_000_000, task_id=task.id)
        self.assertEqual(UsageEvent.objects.filter(tenant=self.tenant, customer=self.customer,
            idempotency_key="idem_dup").count(), 1)
        task.refresh_from_db()
        self.assertEqual(task.event_count, 1)
        self.assertEqual(task.total_billed_cost_micros, 5_000_000)
        self.assertEqual(task.total_provider_cost_micros, 5_000_000)
