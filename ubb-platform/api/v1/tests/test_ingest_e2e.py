"""Task 8: end-to-end burn-to-floor through the FULL async ingestion
pipeline — the closing test of docs/plans/2026-07-03-async-ingestion-hard-
stop-design.md (Rung A core).

Every stage is exercised for real, no mocks:

  REAL POST /api/v1/metering/usage/ingest (accept: estimate -> atomic Redis
  hold -> durable RawIngestEvent append)
    -> REAL settle_raw_events() (exact PricingService.price -> UsageEvent
       insert -> outbox usage.recorded)
    -> REAL process_single_event() driving the REAL billing handler
       (apps.billing.handlers.handle_usage_recorded_billing) so the durable
       Wallet actually moves
    -> REAL LiveCounter.reconcile() MIN-merge.

A single funded owner (prepaid, enforcing, metering_async, $20 wallet) is
burned through the wallet floor via a REAL "per_unit" price card,
$10 / 1,000,000 tokens — exact at every step, so the estimate-then-settle
nets-to-exact property (Task 3's invariant) can be pinned with EQUALITY,
not just an inequality.

Kept as ONE test method (the scenario is inherently sequential/stateful:
batch -> settle -> batch -> settle -> reconcile -> replay) inside ONE test
class, per the task brief.
"""
import redis
from django.conf import settings
from django.db.models import Sum

from apps.billing.gating.services.live_counter import Door, LiveCounter, stop_channel
from apps.billing.queries import read_live_stop
from apps.metering.pricing.tests._helpers import rate_in_default_book
from apps.metering.usage.models import RawIngestEvent, UsageEvent
from apps.metering.usage.tasks import settle_raw_events
from apps.platform.events.models import OutboxEvent
from apps.platform.events.tasks import process_single_event
from apps.platform.tasks.reasons import CUSTOMER_WIDE_STOP

from api.v1.tests.test_ingest_endpoint import IngestEndpointTestBase


def _raw_redis_client():
    return redis.from_url(settings.REDIS_URL)


def _subscribe_stopchan(owner_id):
    """Same idiom as apps/billing/gating/tests/test_hold_lane.py's
    _subscribe(): pin `client` onto the PubSub object so it survives for the
    subscriber's lifetime (PubSub only retains client.connection_pool, not
    client itself — a throwaway local var would be garbage-collected and
    redis.Redis.__del__ tears down the in-use socket, silently losing any
    publish sent during that dead window)."""
    client = _raw_redis_client()
    pubsub = client.pubsub(ignore_subscribe_messages=True)
    pubsub._keepalive_client = client
    pubsub.subscribe(stop_channel(owner_id))
    pubsub.get_message(timeout=1)  # let the SUBSCRIBE round-trip complete
    return pubsub


class AsyncIngestBurnToFloorE2ETest(IngestEndpointTestBase):
    """IngestEndpointTestBase's setUp already gives a prepaid, enforcing,
    metering_async tenant with one customer funded $20,000,000 micros — this
    adds a REAL price card (linear/"per_unit", $10 per 1,000,000 tokens:
    rate_per_unit_micros=10_000_000, unit_quantity=1_000_000 -> exactly
    units*10 micros for any integer units, no rounding slop) so estimation
    goes through the real CardCache/PricingService.estimate path instead of
    the caller-supplied-cost shortcut.
    """

    def setUp(self):
        super().setUp()
        self.card = rate_in_default_book(
            self.tenant, card_type="price", metric_name="tokens",
            pricing_model="per_unit", rate_per_unit_micros=10_000_000,
            unit_quantity=1_000_000)

    def _tokens_event(self, tokens):
        return self._event(billed_cost_micros=None, usage_metrics={"tokens": tokens})

    def _settle_all_pending(self):
        """Drain every pending RawIngestEvent via the REAL settle task, then
        drive every resulting usage.recorded outbox row through the REAL
        billing handler — apps/platform/events/tests/test_tasks.py's idiom
        (call process_single_event directly; do not mock dispatch_to_handlers)
        — so the durable Wallet balance actually moves. TestCase never fires
        transaction.on_commit callbacks on its own, so this is also the only
        way settlement/drawdown happens in this test at all."""
        settle_raw_events()
        for event_id in OutboxEvent.objects.filter(
                event_type="usage.recorded", status="pending"
        ).values_list("id", flat=True):
            process_single_event(str(event_id))

    def test_burn_to_floor_through_full_async_pipeline(self):
        pubsub = _subscribe_stopchan(self.customer.id)
        try:
            # ---- Batch A: two events, no crossing (20M -> 10M). ----
            batch_a = [self._tokens_event(500_000), self._tokens_event(500_000)]
            resp_a = self._post(batch_a)
            self.assertEqual(resp_a.status_code, 200)
            results_a = resp_a.json()["results"]
            self.assertTrue(all(r["accepted"] and not r["stop"] for r in results_a))
            self.assertEqual(sum(r["estimated_cost_micros"] for r in results_a), 10_000_000)
            self.assertIsNone(pubsub.get_message(timeout=0.2))  # no crossing yet

            self._settle_all_pending()
            self.assertEqual(Door.balance(self.customer.id), 10_000_000)

            # ---- Batch B: three events; the SECOND one crosses the floor
            # (10M -> 4M -> -1M -> -3M). This is "the crossing batch" for (c). ----
            batch_b = [self._tokens_event(600_000), self._tokens_event(500_000),
                      self._tokens_event(200_000)]
            resp_b = self._post(batch_b)
            self.assertEqual(resp_b.status_code, 200)
            results_b = resp_b.json()["results"]
            batch_b_estimate_sum = sum(r["estimated_cost_micros"] for r in results_b)
            self.assertEqual(batch_b_estimate_sum, 13_000_000)
            self.assertTrue(all(r["accepted"] for r in results_b))  # cooperative (I3):
            # the crossing hold itself is never rejected/rolled back.

            # (a) the crossing item's verdict.
            self.assertTrue(results_b[1]["stop"])
            self.assertEqual(results_b[1]["stop_reason"], CUSTOMER_WIDE_STOP)
            self.assertEqual(results_b[1]["stop_scope"], "customer")
            # (b) every subsequent item in the same batch.
            self.assertTrue(results_b[2]["stop"])
            self.assertEqual(results_b[2]["stop_reason"], CUSTOMER_WIDE_STOP)
            # LiveCounter.hold pipelines the WHOLE batch's Redis holds
            # first, THEN determines crossing from the full set of post-hold
            # values, THEN reads the flag ONCE and applies that single
            # verdict to every held item in the call -- so item 0 (which did
            # not itself cross) also reports stop=True. This is deliberate,
            # documented batch-granularity cooperative behavior (see
            # the hold lane's `verdict = read(...); for o in out: ...
            # o.update(verdict)`), not a bug -- pinned here so a future
            # regression toward "only positionally-crossing items get
            # flagged" is caught.
            self.assertTrue(results_b[0]["stop"])

            # (c) overage bound: the live balance at the flag-set instant
            # (== immediately after this one pipelined batch, since the flag
            # can only be set AFTER every item's Redis op in the batch has
            # already executed) never exceeds the crossing batch's own total
            # estimate -- the spec's "~1 batch estimate" bound.
            live_balance_at_flag_set = Door.balance(self.customer.id)
            self.assertEqual(live_balance_at_flag_set, -3_000_000)
            self.assertLessEqual(abs(live_balance_at_flag_set), batch_b_estimate_sum)

            # (f) exactly one pub/sub message and exactly one StopFired
            # outbox row -- the unset->set TRANSITION only, no spam.
            msg = pubsub.get_message(timeout=1)
            self.assertIsNotNone(msg)
            self.assertEqual(msg["type"], "message")
            self.assertEqual(msg["data"].decode(), CUSTOMER_WIDE_STOP)
            self.assertIsNone(pubsub.get_message(timeout=0.2))  # exactly one message
            self.assertEqual(OutboxEvent.objects.filter(event_type="stop.fired").count(), 1)
            stop_fired = OutboxEvent.objects.get(event_type="stop.fired")
            self.assertEqual(stop_fired.payload["owner_id"], str(self.customer.id))
            self.assertEqual(stop_fired.payload["reason"], CUSTOMER_WIDE_STOP)

            # (g) the stop flag is durably readable via the read_live_stop
            # cross-product port (not just the ack that happened to carry it).
            verdict = read_live_stop(self.customer.id, self.tenant)
            self.assertTrue(verdict["stop"])
            self.assertEqual(verdict["stop_reason"], CUSTOMER_WIDE_STOP)
            self.assertEqual(verdict["stop_scope"], "customer")

            # ---- (d) settle everything + process outbox + reconcile:
            # exact convergence (the linear card estimates exactly, so
            # estimate-then-settle nets to EQUALITY, not just an inequality). ----
            self._settle_all_pending()
            self.wallet.refresh_from_db()
            durable_balance = self.wallet.balance_micros
            total_billed = UsageEvent.objects.aggregate(
                total=Sum("billed_cost_micros"))["total"]
            self.assertEqual(total_billed, 23_000_000)
            self.assertEqual(total_billed, 20_000_000 - durable_balance)
            self.assertEqual(durable_balance, -3_000_000)

            LiveCounter.reconcile(self.customer.id, self.tenant)
            self.assertEqual(Door.balance(self.customer.id), durable_balance)

            self.assertEqual(RawIngestEvent.objects.filter(status="settled").count(), 5)
            self.assertEqual(UsageEvent.objects.count(), 5)

            # ---- (e) whole-batch replay of the FINAL batch: zero new
            # UsageEvent rows, zero new holds (live counter unchanged), every
            # item reports duplicate_suspect. ----
            usage_count_before = UsageEvent.objects.count()
            balance_before_replay = Door.balance(self.customer.id)

            replay_resp = self._post(batch_b)  # identical customer_id + idempotency_key
            self.assertEqual(replay_resp.status_code, 200)
            for r in replay_resp.json()["results"]:
                self.assertTrue(r["accepted"])
                self.assertTrue(r["duplicate_suspect"])
                self.assertTrue(r["stop"])  # the flag is still set -> still surfaced
            # No new hold taken by the replay's accept-layer idem hit.
            self.assertEqual(Door.balance(self.customer.id),
                             balance_before_replay)

            # Drain the replay's held=False raws through settle too: this
            # exercises the settle-time exactly-once guarantee (the
            # UsageEvent unique constraint), not just the accept-layer idem
            # prefilter -- a materially stronger assertion than "we never
            # even tried to settle the replay".
            self._settle_all_pending()
            self.assertEqual(UsageEvent.objects.count(), usage_count_before)
            self.assertEqual(Door.balance(self.customer.id),
                             balance_before_replay)
            self.assertEqual(RawIngestEvent.objects.filter(status="duplicate").count(), 3)
            self.assertEqual(RawIngestEvent.objects.count(), 8)  # 2 + 3 + 3 replay
        finally:
            pubsub.close()
