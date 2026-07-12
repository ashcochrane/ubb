"""Task 6: Settlement — settle_raw / settle_raw_events / accumulate_cost_settled.

Turns accepted RawIngestEvent rows (Task 5's async ingest path) into
exactly-priced, durably-recorded UsageEvents, and converges the live Redis
counter by (estimate - exact). Idempotency across the accept/settle boundary
(the UsageEvent unique constraint) is the core requirement.

Reuses IngestEndpointTestBase (api/v1/tests/test_ingest_endpoint.py) for the
strongest tests: real raws produced by the real /usage/ingest endpoint. A few
tests construct RawIngestEvent rows directly to reach edge cases the endpoint
cannot reliably reproduce on demand (a genuine duplicate hold, a crash-orphan
hold, a poison payload).
"""
from unittest.mock import patch

from django.utils import timezone

from apps.billing.gating.services.live_ledger_service import LiveLedgerService
from apps.billing.queries import acquire_ingest_holds
from apps.metering.pricing.tests._helpers import rate_in_default_book
from apps.metering.usage.models import BackfillDirtyPeriod, RawIngestEvent, UsageEvent
from apps.metering.usage.services.usage_service import UsageService
from apps.metering.usage.tasks import MAX_SETTLE_ATTEMPTS, settle_raw_events
from apps.platform.events.models import OutboxEvent
from apps.platform.runs.models import Run

from api.v1.tests.test_ingest_endpoint import IngestEndpointTestBase


class SettlementTestBase(IngestEndpointTestBase):
    """Adds a RawIngestEvent constructor for tests that need to reach states
    the real endpoint cannot reliably reproduce on demand."""

    def _raw(self, **overrides):
        base = dict(
            tenant=self.tenant, customer=self.customer,
            billing_owner_id=self.customer.id, run_id=None,
            idempotency_key="k1", payload={"request_id": "r1"},
            estimate_micros=0, estimate_exact=False, held=True,
            status="pending",
        )
        base.update(overrides)
        return RawIngestEvent.objects.create(**base)


class NetsToExactTest(SettlementTestBase):
    """(a) settle nets to exact; (e) tier mirror written to units_total_after.

    A decreasing graduated ladder (10/unit up to 1_000_000 units, then
    8/unit) whose event straddles both tiers: EstimationService's
    max-applicable-rate safety margin forces a genuine over-estimate (the
    mirror is unset -> prior=0, so the base marginal already equals the exact
    price; the "worst rate over the whole quantity" term is what pushes the
    hold above it) — an over-hold at a REAL tiered card, produced by the REAL
    accept path, settled through the real settle_raw.
    """

    def setUp(self):
        super().setUp()
        self.card = rate_in_default_book(
            self.tenant, card_type="price", metric_name="tokens",
            pricing_model="graduated",
            tiers=[
                {"up_to": 1_000_000, "rate_per_unit_micros": 10_000_000},
                {"up_to": None, "rate_per_unit_micros": 8_000_000},
            ])

    def test_settle_nets_to_exact_and_writes_tier_mirror(self):
        event = self._event(billed_cost_micros=None,
                            usage_metrics={"tokens": 1_200_000})
        resp = self._post([event])
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["results"][0]["accepted"])

        raw = RawIngestEvent.objects.get()
        self.assertTrue(raw.held)
        estimate = raw.estimate_micros
        # Genuine over-hold: EstimationService's max-applicable-rate guard
        # prices the FULL 1_200_000 units at the higher (10/unit) tier rate.
        self.assertGreater(estimate, 0)

        result = UsageService.settle_raw(raw)
        self.assertEqual(result, "settled")

        exact = UsageEvent.objects.get()
        # Exact marginal: 1_000_000 @ 10 + 200_000 @ 8 (unit_quantity 1_000_000
        # default) = 10_000_000 + 1_600_000.
        self.assertEqual(exact.billed_cost_micros, 11_600_000)
        self.assertGreater(estimate, exact.billed_cost_micros)  # confirms a real delta

        raw.refresh_from_db()
        self.assertEqual(raw.status, "settled")

        # PROPERTY: accept-hold + settle-delta nets EXACTLY to what a single
        # synchronous debit of the exact cost would have produced.
        self.assertEqual(
            LiveLedgerService.read_prepaid(self.customer.id),
            self.wallet.balance_micros - exact.billed_cost_micros,
        )

        # (e) tier mirror keyed by the event's effective (== settle-time,
        # since no effective_at was supplied) month, holding units_total_after.
        from apps.metering.pricing.services.card_cache import TierMirror
        mirrored = TierMirror.read(self.tenant.id, self.customer.id,
                                   str(self.card.lineage_id), timezone.now())
        self.assertEqual(mirrored, 1_200_000)

        # Single UsageEvent, single outbox row.
        self.assertEqual(UsageEvent.objects.count(), 1)
        self.assertEqual(OutboxEvent.objects.filter(event_type="usage.recorded").count(), 1)


class DuplicateSettleTest(SettlementTestBase):
    """(b) A second, independently-HELD raw sharing an idempotency_key (e.g.
    the Redis idem key expired between two accept requests, so the second one
    took its own real hold) settles as "duplicate": the second UsageEvent
    insert hits the unique constraint, the second hold is fully released, and
    no second outbox row is written."""

    def test_duplicate_raw_releases_hold_no_second_event(self):
        owner_id = self.customer.id
        payload = {"request_id": "r1", "billed_cost_micros": 500_000,
                  "provider_cost_micros": 0}

        acquire_ingest_holds(owner_id, self.tenant,
                            [{"estimate_micros": 500_000, "run_id": None,
                              "run_cap_micros": None, "run_seed_micros": 0}])
        raw1 = self._raw(idempotency_key="dup-key", payload=payload,
                        estimate_micros=500_000, held=True)
        self.assertEqual(UsageService.settle_raw(raw1), "settled")
        balance_after_first = LiveLedgerService.read_prepaid(owner_id)
        self.assertEqual(balance_after_first, self.wallet.balance_micros - 500_000)

        acquire_ingest_holds(owner_id, self.tenant,
                            [{"estimate_micros": 500_000, "run_id": None,
                              "run_cap_micros": None, "run_seed_micros": 0}])
        self.assertEqual(LiveLedgerService.read_prepaid(owner_id),
                        balance_after_first - 500_000)
        raw2 = self._raw(idempotency_key="dup-key", payload=payload,
                        estimate_micros=500_000, held=True)

        result = UsageService.settle_raw(raw2)
        self.assertEqual(result, "duplicate")
        raw2.refresh_from_db()
        self.assertEqual(raw2.status, "duplicate")

        self.assertEqual(UsageEvent.objects.count(), 1)
        self.assertEqual(OutboxEvent.objects.filter(event_type="usage.recorded").count(), 1)
        # The second hold is fully credited back -> balance returns to
        # exactly what it was after the FIRST settle.
        self.assertEqual(LiveLedgerService.read_prepaid(owner_id), balance_after_first)


class SettleAfterRunKillTest(SettlementTestBase):
    """(c) A settle landing after the run was killed must still record true
    cost against the run's total, and must never raise."""

    def test_settle_after_kill_records_cost_no_exception(self):
        run = Run.objects.create(
            tenant=self.tenant, customer=self.customer, status="active",
            balance_snapshot_micros=20_000_000, billing_owner_id=self.customer.id)
        resp = self._post([self._event(run_id=str(run.id), billed_cost_micros=500_000)])
        self.assertEqual(resp.status_code, 200)
        raw = RawIngestEvent.objects.get()
        self.assertTrue(raw.held)

        Run.objects.filter(id=run.id).update(status="killed")

        result = UsageService.settle_raw(raw)  # must not raise
        self.assertEqual(result, "settled")

        run.refresh_from_db()
        self.assertEqual(run.status, "killed")             # untouched
        self.assertEqual(run.total_cost_micros, 500_000)   # true cost still recorded
        self.assertEqual(run.event_count, 1)
        self.assertIsNotNone(run.last_event_at)


class PoisonEventTest(SettlementTestBase):
    """(d) A payload that can never price successfully (strict cost coverage,
    no matching cost card) is marked "failed" after MAX_SETTLE_ATTEMPTS
    attempts, its hold is released, and an ERROR is logged."""

    def test_poison_payload_fails_after_max_attempts_and_releases_hold(self):
        self.tenant.require_cost_card_coverage = True
        self.tenant.save(update_fields=["require_cost_card_coverage"])
        owner_id = self.customer.id
        acquire_ingest_holds(owner_id, self.tenant,
                            [{"estimate_micros": 250_000, "run_id": None,
                              "run_cap_micros": None, "run_seed_micros": 0}])
        balance_after_hold = LiveLedgerService.read_prepaid(owner_id)
        self.assertEqual(balance_after_hold, self.wallet.balance_micros - 250_000)

        raw = self._raw(idempotency_key="poison-key",
                       payload={"request_id": "r1", "usage_metrics": {"tokens": 100}},
                       estimate_micros=250_000, held=True)

        for attempt in range(1, MAX_SETTLE_ATTEMPTS):
            settle_raw_events()
            raw.refresh_from_db()
            self.assertEqual(raw.status, "pending")
            self.assertEqual(raw.attempts, attempt)

        with self.assertLogs("ubb.metering", level="ERROR") as logs:
            settle_raw_events()
        self.assertTrue(any("settle_raw.poisoned" in m for m in logs.output))

        raw.refresh_from_db()
        self.assertEqual(raw.status, "failed")
        self.assertEqual(raw.attempts, MAX_SETTLE_ATTEMPTS)
        self.assertEqual(UsageEvent.objects.count(), 0)
        # The hold is released -> balance returns to its pre-hold value.
        self.assertEqual(LiveLedgerService.read_prepaid(owner_id), self.wallet.balance_micros)


class OrphanHoldUnheldBranchTest(SettlementTestBase):
    """(f) held=False branch (idem-hit-at-accept retry-append case) applies a
    FULL debit so the live counter converges for the common case (the first
    append genuinely settled already -> this hits IntegrityError -> duplicate,
    covered by DuplicateSettleTest's sibling shape). The IMPLEMENTER NOTE's
    documented edge case: if the FIRST append was truly LOST (a crash between
    the hold and the durable append), this row is the only survivor, and the
    orphaned hold already decremented the live counter once — the full debit
    here double-counts against it. This is NOT fixed locally (spec invariant
    7): the hourly reconcile_prepaid MIN-merge is documented as the corrector.
    This test pins what that merge ACTUALLY does — MIN-merge only ever
    LOWERS toward the durable balance, so an OVER-restrictive live counter
    (already below durable) is left exactly as-is (a fixed point, not
    retroactively corrected upward) — the "fails safe" contract by design.
    """

    def test_orphan_hold_double_counts_and_reconcile_leaves_it_at_its_fixed_point(self):
        owner_id = self.customer.id
        self.wallet.balance_micros = 50_000_000
        self.wallet.save(update_fields=["balance_micros"])

        # The FIRST (crashed) attempt: its hold is taken (decrementing the
        # live counter) but — by construction — no RawIngestEvent for it ever
        # exists (the process died before the durable append).
        acquire_ingest_holds(owner_id, self.tenant,
                            [{"estimate_micros": 5_000_000, "run_id": None,
                              "run_cap_micros": None, "run_seed_micros": 0}])
        self.assertEqual(LiveLedgerService.read_prepaid(owner_id), 45_000_000)

        # The RETRY's raw: the idem key was already SET by the crashed
        # attempt, so accept treated it as an idem-hit -> held=False.
        raw = self._raw(idempotency_key="orphan-key", held=False, estimate_micros=0,
                       payload={"request_id": "r1", "billed_cost_micros": 10_000_000,
                               "provider_cost_micros": 0})

        result = UsageService.settle_raw(raw)
        self.assertEqual(result, "settled")
        self.assertEqual(UsageEvent.objects.count(), 1)
        # Full debit applied on top of the still-live orphan hold.
        live_after_settle = LiveLedgerService.read_prepaid(owner_id)
        self.assertEqual(live_after_settle, 45_000_000 - 10_000_000)

        # Simulate the durable wallet reflecting the ONE real debit (what the
        # async drawdown handler would apply from the settle's outbox event).
        self.wallet.balance_micros -= 10_000_000
        self.wallet.save(update_fields=["balance_micros"])
        durable = self.wallet.balance_micros
        self.assertGreater(durable, live_after_settle)  # over-restrictive, as documented

        LiveLedgerService.reconcile_prepaid(owner_id, self.tenant)
        after_first_reconcile = LiveLedgerService.read_prepaid(owner_id)
        # MIN-merge only lowers; durable > live here, so it is a no-op.
        self.assertEqual(after_first_reconcile, live_after_settle)

        # Convergence: the value is a fixed point of the merge (idempotent
        # under repeated reconcile calls), not merely unchanged once.
        LiveLedgerService.reconcile_prepaid(owner_id, self.tenant)
        self.assertEqual(LiveLedgerService.read_prepaid(owner_id), after_first_reconcile)


class EnqueueOnCommitTest(IngestEndpointTestBase):
    """(g) A successful ingest enqueues settle_raw_events on commit."""

    def test_ingest_enqueues_settle_raw_events_on_commit(self):
        with patch("apps.metering.usage.tasks.settle_raw_events.delay") as mock_delay:
            with self.captureOnCommitCallbacks(execute=True):
                resp = self._post([self._event(billed_cost_micros=100_000)])
        self.assertEqual(resp.status_code, 200)
        mock_delay.assert_called_once()

    def test_no_raws_appended_does_not_enqueue(self):
        with patch("apps.metering.usage.tasks.settle_raw_events.delay") as mock_delay:
            with self.captureOnCommitCallbacks(execute=True):
                # currency mismatch -> rejected locally, no raw ever appended
                self._post([self._event(currency="eur", billed_cost_micros=100_000)])
        mock_delay.assert_not_called()


class EffectiveAtSettleTest(SettlementTestBase):
    """(h) effective_at settle prices as_of, preserves it on the UsageEvent,
    marks a BackfillDirtyPeriod for the prior month, and normalizes the
    outbox UsageRecorded effective_at to UTC."""

    def test_backdated_settle_prices_as_of_and_marks_dirty_period(self):
        self.tenant.backfill_window_days = 60
        self.tenant.save(update_fields=["backfill_window_days"])
        now = timezone.now()
        first_of_this_month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        eff = first_of_this_month - timezone.timedelta(days=1)  # last instant, prior month

        resp = self._post([self._event(billed_cost_micros=300_000,
                                       effective_at=eff.isoformat())])
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["results"][0]["accepted"])
        raw = RawIngestEvent.objects.get()
        self.assertTrue(raw.held)

        result = UsageService.settle_raw(raw)
        self.assertEqual(result, "settled")

        event = UsageEvent.objects.get()
        self.assertEqual(event.effective_at, eff)

        self.assertTrue(BackfillDirtyPeriod.objects.filter(
            tenant=self.tenant, customer=self.customer,
            period_start=eff.date().replace(day=1)).exists())

        outbox = OutboxEvent.objects.get(event_type="usage.recorded")
        from datetime import timezone as dt_timezone
        self.assertEqual(outbox.payload["effective_at"],
                         eff.astimezone(dt_timezone.utc).isoformat())


class DuplicateRaceExactlyOnceReleaseTest(SettlementTestBase):
    """Two workers racing the SAME held duplicate raw must release its hold
    exactly once. The IntegrityError rolls back settle_raw's atomic — dropping
    the top-of-function row lock while DB status is still "pending" — so the
    duplicate resolution must re-lock and let only the pending -> duplicate
    flip WINNER release. The race is simulated deterministically: the winner
    resolves the row (flip + release) in the exact rollback -> re-lock gap the
    fix closes, injected via a call-counting select_for_update wrapper."""

    def test_racing_duplicate_resolution_releases_hold_exactly_once(self):
        from apps.billing.queries import release_ingest_hold
        owner_id = self.customer.id
        payload = {"request_id": "r1", "billed_cost_micros": 500_000,
                   "provider_cost_micros": 0}

        acquire_ingest_holds(owner_id, self.tenant,
                             [{"estimate_micros": 500_000, "run_id": None,
                               "run_cap_micros": None, "run_seed_micros": 0}])
        raw1 = self._raw(idempotency_key="race-key", payload=payload,
                         estimate_micros=500_000, held=True)
        self.assertEqual(UsageService.settle_raw(raw1), "settled")
        balance_after_first = LiveLedgerService.read_prepaid(owner_id)

        acquire_ingest_holds(owner_id, self.tenant,
                             [{"estimate_micros": 500_000, "run_id": None,
                               "run_cap_micros": None, "run_seed_micros": 0}])
        raw2 = self._raw(idempotency_key="race-key", payload=payload,
                         estimate_micros=500_000, held=True)
        self.assertEqual(LiveLedgerService.read_prepaid(owner_id),
                         balance_after_first - 500_000)

        real_sfu = RawIngestEvent.objects.select_for_update
        calls = {"n": 0}

        def interleaved_sfu(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 2:
                # call 1 = settle_raw's top lock; call 2 = the duplicate
                # resolution's re-lock — i.e. the loser is now in the
                # rollback -> re-lock gap. The RACING WINNER resolves the raw
                # here: flips it and releases the hold, exactly what a second
                # settle_raw_events invocation would have done.
                RawIngestEvent.objects.filter(
                    id=raw2.id, status="pending").update(status="duplicate")
                release_ingest_hold(owner_id, self.tenant, None, 500_000)
            return real_sfu(*args, **kwargs)

        with patch.object(RawIngestEvent.objects, "select_for_update",
                          side_effect=interleaved_sfu):
            result = UsageService.settle_raw(raw2)

        # The loser's except path DID re-lock (the fix exists)...
        self.assertEqual(calls["n"], 2)
        self.assertEqual(result, "duplicate")
        raw2.refresh_from_db()
        self.assertEqual(raw2.status, "duplicate")
        self.assertEqual(UsageEvent.objects.count(), 1)
        # ...and did NOT release again: exactly ONE release (the winner's) —
        # a double release would leave the balance 500_000 ABOVE this.
        self.assertEqual(LiveLedgerService.read_prepaid(owner_id), balance_after_first)


class PoisonRaceExactlyOnceReleaseTest(SettlementTestBase):
    """Same exactly-once discipline for the poison bookkeeping path: the
    task's failure handler must re-lock the raw and skip (no attempts bump, no
    release) when a racing invocation resolved it in the settle-rollback ->
    bookkeeping gap."""

    def test_stale_poison_worker_skips_resolved_raw_without_second_release(self):
        from apps.billing.queries import release_ingest_hold
        owner_id = self.customer.id
        acquire_ingest_holds(owner_id, self.tenant,
                             [{"estimate_micros": 250_000, "run_id": None,
                               "run_cap_micros": None, "run_seed_micros": 0}])
        raw = self._raw(idempotency_key="poison-race-key",
                        payload={"request_id": "r1"},
                        estimate_micros=250_000, held=True)
        self.assertEqual(LiveLedgerService.read_prepaid(owner_id),
                         self.wallet.balance_micros - 250_000)

        real_sfu = RawIngestEvent.objects.select_for_update
        calls = {"n": 0}

        def interleaved_sfu(*args, **kwargs):
            calls["n"] += 1
            if calls["n"] == 2:
                # call 1 = the task's batch claim; call 2 = the failure
                # handler's re-lock (settle_raw itself is patched to raise
                # before touching the DB). The RACING WINNER resolves the raw
                # as poisoned — flips it and releases — in the gap.
                RawIngestEvent.objects.filter(
                    id=raw.id, status="pending").update(
                        status="failed", attempts=MAX_SETTLE_ATTEMPTS)
                release_ingest_hold(owner_id, self.tenant, None, 250_000)
            return real_sfu(*args, **kwargs)

        with patch.object(UsageService, "settle_raw",
                          side_effect=RuntimeError("simulated settle crash")), \
             patch.object(RawIngestEvent.objects, "select_for_update",
                          side_effect=interleaved_sfu):
            settle_raw_events()

        # The handler DID re-lock (the fix exists)...
        self.assertEqual(calls["n"], 2)
        raw.refresh_from_db()
        self.assertEqual(raw.status, "failed")
        # ...took no unlocked read-modify-write over the winner's attempts...
        self.assertEqual(raw.attempts, MAX_SETTLE_ATTEMPTS)
        # ...and released nothing itself: exactly ONE release (the winner's).
        self.assertEqual(LiveLedgerService.read_prepaid(owner_id),
                         self.wallet.balance_micros)


class WideIdempotencyKeyTest(SettlementTestBase):
    """Final-review fix batch #1: RawIngestEvent.idempotency_key must accept
    keys up to 500 chars (matching the API schema's max_length=500 and
    UsageEvent.idempotency_key's own width) — a 256-500 char caller key used
    to DataError the whole batch's bulk_create, and the endpoint's only
    failure-recovery path is "the client retries", so that error was
    permanent, not transient."""

    def test_400_char_idempotency_key_ingests_and_settles_cleanly(self):
        long_key = "k" * 400
        event = self._event(billed_cost_micros=250_000, idempotency_key=long_key)

        resp = self._post([event])
        self.assertEqual(resp.status_code, 200)
        r = resp.json()["results"][0]
        self.assertTrue(r["accepted"])

        raw = RawIngestEvent.objects.get()
        self.assertEqual(raw.idempotency_key, long_key)
        self.assertTrue(raw.held)

        result = UsageService.settle_raw(raw)
        self.assertEqual(result, "settled")
        event_row = UsageEvent.objects.get()
        self.assertEqual(event_row.idempotency_key, long_key)
        self.assertEqual(event_row.billed_cost_micros, 250_000)


class SettleRawEventsTaskTest(SettlementTestBase):
    """Direct coverage of the task's own claim/loop/re-enqueue control flow,
    beyond what the settle_raw-focused tests above exercise."""

    def test_task_settles_multiple_real_raws_and_returns_count(self):
        resp = self._post([
            self._event(billed_cost_micros=100_000),
            self._event(billed_cost_micros=200_000),
        ])
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(RawIngestEvent.objects.filter(status="pending").count(), 2)

        settled_count = settle_raw_events()

        self.assertEqual(settled_count, 2)
        self.assertEqual(RawIngestEvent.objects.filter(status="settled").count(), 2)
        self.assertEqual(UsageEvent.objects.count(), 2)

    def test_task_reenqueues_itself_when_claim_drains_a_full_batch(self):
        self._post([
            self._event(billed_cost_micros=100_000),
            self._event(billed_cost_micros=200_000),
        ])
        self.assertEqual(RawIngestEvent.objects.filter(status="pending").count(), 2)

        with patch("apps.metering.usage.tasks.settle_raw_events.delay") as mock_delay:
            settle_raw_events(batch_size=1)  # claims exactly 1 of 2 -> more waiting
        mock_delay.assert_called_once_with(batch_size=1)
        self.assertEqual(RawIngestEvent.objects.filter(status="settled").count(), 1)
        self.assertEqual(RawIngestEvent.objects.filter(status="pending").count(), 1)

    def test_task_does_not_reenqueue_when_batch_not_full(self):
        self._post([self._event(billed_cost_micros=100_000)])

        with patch("apps.metering.usage.tasks.settle_raw_events.delay") as mock_delay:
            settle_raw_events(batch_size=200)
        mock_delay.assert_not_called()
