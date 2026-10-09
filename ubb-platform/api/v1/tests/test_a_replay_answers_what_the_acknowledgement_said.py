"""An idempotent replay answers ONLY from what the original acknowledgement
said (#569; the owner's and consultant's rulings of 2026-10-08).

Every recorded result keeps an insert-only stop acknowledgement — `stop`
true or false, written in the same transaction as its posting — holding the
stop facts it returned, the ceiling assessment beside them, and which unit
or which customer's line the stop was about. A replay reads that record and
NOTHING ELSE for those fields: never the live stop flag, the unit of work,
a Pool, configuration, a counter or the posting's itemised stop context.
So, confirmed knowingly:

  * an original `stop: false` replays `stop: false`, even when the customer
    or the work has been stopped since;
  * an original stop replays with its original mechanism, reason, scope,
    bound and measured amount, even when every live fact has moved — the
    bound reconfigured, the amount grown, the work ended, the stop cleared,
    a new episode opened;
  * the ceiling assessment is the original's (it was "where the unit stands
    NOW" under #452; ADR-0019 records the departure);
  * #609's precedence is replayed exactly as it was originally selected.

The pins run on both recording routes (a mixin bound twice), a key first
recorded on one route replays identically on the other, and the record's
own rules — insert-only at the database, written with its posting, never
reconstructed when missing — are pinned beneath them.
"""
import json
import uuid
from unittest import mock

from django.db import (DatabaseError, IntegrityError, connection, models,
                       transaction)

from api.v1.tests.test_a_stop_acknowledgement_says_what_stopped_it import (
    STOP_FACTS, ReadsAStopAcknowledgement)
from apps.billing.gating.services.live_counter import Door, LiveCounter
from apps.billing.gating.tests.test_a_blocking_pool_stops_prepaid_work_as_it_stops_postpaid import (
    DOORBELL, SOLD_WHOLE, THE_AGREED_PRICE, PoolTestBase, ThroughABatchItem,
    ThroughTheSingleRoute)
from apps.metering.pricing.tests._helpers import a_price_for_whole_work
from apps.metering.usage.models import Posting, StopAcknowledgement
from apps.metering.usage.tests._helpers import rule_on_the_table
from apps.metering.usage.services.usage_service import (
    StopAcknowledgementMissing, UsageService)
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
from apps.platform.work import reasons
from apps.platform.work.models import Task, TaskType
from core.vocabulary import (
    CEILING_STATUS_CEILING_REACHED, CEILING_STATUS_WITHIN_CEILING,
    PRICING_MODE_FIXED, SPEND_POOL_ENFORCE_MODE_BLOCKING,
    TASK_OUTCOME_DELIVERED, TASK_STATUS_KILLED, TASK_TYPE_KIND_TASK,
    TRIGGER_SOURCE_USAGE_INGEST)

#: The ceiling assessment beside the stop facts — also the original's on a
#: replay (ADR-0019 §5).
ASSESSMENT = ("ceiling_status", "ceiling_used_percentage",
              "ceiling_remaining_micros")


class MovesTheLiveFactsOn(ReadsAStopAcknowledgement):
    """The tenant's own doors for moving a bound after an acknowledgement:
    the Pool's and the floor's configuration routes, and the hourly pass."""

    def _put_pool(self, customer, *, cap, pct):
        response = self.http.put(
            f"/api/v1/billing/customers/{customer.id}/customer-spend-pool",
            data=json.dumps({"cap_micros": cap, "hard_stop_pct": pct,
                             "enforce_mode": SPEND_POOL_ENFORCE_MODE_BLOCKING}),
            **self._headers())
        self.assertEqual(response.status_code, 200, response.content)

    def _put_floor(self, customer, floor):
        response = self.http.put(
            f"/api/v1/billing/customers/{customer.id}/billing-profile",
            data=json.dumps({"min_balance_micros": floor}), **self._headers())
        self.assertEqual(response.status_code, 200, response.content)

    def _clear_the_owner_level(self, owner):
        """The hourly owner-level pass, under the Pool the tenant has just
        raised: the line is cleared and the flag lifts (or re-points)."""
        with mock.patch(DOORBELL), self.captureOnCommitCallbacks(execute=True):
            LiveCounter.reconcile(owner.id, self.tenant)


class AReplayAnswersWhatTheAcknowledgementSaid(MovesTheLiveFactsOn):
    """The shared shape: each pin records under a key, moves the live facts
    on, and replays the key. Each binding supplies `_through_the_route`."""

    def _key(self):
        return f"idem-{uuid.uuid4()}"

    def _assert_replayed(self, replayed, original):
        """The replay is the original event, and says exactly what the
        original said about stopping — every stop fact and the assessment."""
        self.assertEqual(replayed["event_id"], original["event_id"])
        self.assertEqual({key: replayed[key] for key in STOP_FACTS + ASSESSMENT},
                         {key: original[key] for key in STOP_FACTS + ASSESSMENT})

    def _a_pool_stop(self, key):
        self._pool_line(self.customer, cap=10_000_000, pct=80)
        original = self._report(bills=9_000_000, idempotency_key=key)
        self._assert_stopped(original, reasons.CUSTOMER_SPEND_POOL, "customer",
                             TRIGGER_SOURCE_USAGE_INGEST,
                             bound=8_000_000, measured=9_000_000)
        return original

    def _a_ceiling_stop(self, key):
        unit = self._unit(task_cogs_ceiling_micros=5_000_000)
        original = self._report(task_id=unit, provider_cost_micros=5_500_000,
                                idempotency_key=key)
        self._assert_stopped(original, reasons.TASK_COGS_CEILING, "task",
                             TRIGGER_SOURCE_USAGE_INGEST,
                             bound=5_000_000, measured=5_500_000)
        self.assertEqual(original["ceiling_status"],
                         CEILING_STATUS_CEILING_REACHED)
        return unit, original

    # -- 1. the bound changed after the original ----------------------------

    def test_a_pool_reconfigured_since_replays_the_original_bound(self):
        key = self._key()
        original = self._a_pool_stop(key)
        self._put_pool(self.customer, cap=20_000_000, pct=50)

        self._assert_replayed(self._report(idempotency_key=key), original)

    def test_a_floor_reconfigured_since_replays_the_original_bound(self):
        key = self._key()
        self._wallet(self.customer, 3_000_000, floor=1_000_000)
        original = self._report(bills=4_500_000, idempotency_key=key)
        self._assert_stopped(original, reasons.HARD_FLOOR, "customer",
                             TRIGGER_SOURCE_USAGE_INGEST,
                             bound=-1_000_000, measured=-1_500_000)
        self._put_floor(self.customer, 4_000_000)

        self._assert_replayed(self._report(idempotency_key=key), original)

    def test_a_ceiling_rewritten_on_the_row_replays_the_original_bound(self):
        """Nothing writes a unit's pinned ceiling after its start, so the row
        is written directly — to prove the replay never reads it."""
        key = self._key()
        unit, original = self._a_ceiling_stop(key)
        Task.objects.filter(id=unit).update(task_cogs_ceiling_micros=50_000_000)

        self._assert_replayed(self._report(idempotency_key=key), original)

    # -- 2. the measured amount moved on ------------------------------------

    def test_more_cogs_since_replays_the_original_measured_amount(self):
        key = self._key()
        unit, original = self._a_ceiling_stop(key)
        self._report(task_id=unit, provider_cost_micros=2_000_000)
        self.assertEqual(Task.objects.get(id=unit).total_provider_cost_micros,
                         7_500_000)

        self._assert_replayed(self._report(idempotency_key=key), original)

    def test_more_charges_since_replays_the_original_measured_amount(self):
        key = self._key()
        original = self._a_pool_stop(key)
        self._report(bills=3_000_000)

        self._assert_replayed(self._report(idempotency_key=key), original)

    # -- 3. the work or the customer moved state ----------------------------

    def test_work_stopped_at_its_ceiling_and_ended_since_replays_its_stop(self):
        """Today's replay lost the unit's verdict and said `stop: false`; the
        work has ended since, and the replay still names the ceiling."""
        key = self._key()
        unit, original = self._a_ceiling_stop(key)
        self.assertEqual(Task.objects.get(id=unit).status, TASK_STATUS_KILLED)

        self._assert_replayed(self._report(idempotency_key=key), original)

    def test_a_customer_stop_cleared_since_still_replays_stopped(self):
        key = self._key()
        original = self._a_pool_stop(key)
        self._put_pool(self.customer, cap=100_000_000, pct=100)
        self._clear_the_owner_level(self.customer)
        self._assert_not_stopped(self._report())

        self._assert_replayed(self._report(idempotency_key=key), original)

    def test_an_original_no_stop_replays_no_stop_though_the_customer_is_stopped(self):
        key = self._key()
        self._pool_line(self.customer, cap=10_000_000, pct=80)
        original = self._report(bills=1_000_000, idempotency_key=key)
        self._assert_not_stopped(original)
        self.assertTrue(self._report(bills=8_000_000)["stop"])

        replayed = self._report(idempotency_key=key)

        self._assert_not_stopped(replayed)
        self._assert_replayed(replayed, original)

    # -- 5. an episode closed and a new one opened --------------------------

    def test_a_new_episode_since_does_not_leak_into_the_replay(self):
        key = self._key()
        original = self._a_pool_stop(key)
        self._put_pool(self.customer, cap=100_000_000, pct=100)
        self._clear_the_owner_level(self.customer)
        self._put_pool(self.customer, cap=10_000_000, pct=50)
        reopened = self._report(bills=1_000_000)
        self._assert_stopped(reopened, reasons.CUSTOMER_SPEND_POOL, "customer",
                             TRIGGER_SOURCE_USAGE_INGEST,
                             bound=5_000_000, measured=10_000_000)

        self._assert_replayed(self._report(idempotency_key=key), original)

    # -- 6. the ceiling assessment is the original's ------------------------

    def test_the_ceiling_assessment_on_a_replay_is_the_originals(self):
        key = self._key()
        unit = self._unit(task_cogs_ceiling_micros=10_000_000)
        original = self._report(task_id=unit, provider_cost_micros=4_000_000,
                                idempotency_key=key)
        self.assertEqual(
            {k: original[k] for k in ASSESSMENT},
            {"ceiling_status": CEILING_STATUS_WITHIN_CEILING,
             "ceiling_used_percentage": 40,
             "ceiling_remaining_micros": 6_000_000})
        self._report(task_id=unit, provider_cost_micros=6_000_000)

        replayed = self._report(idempotency_key=key)

        self._assert_replayed(replayed, original)
        self.assertIsNone(replayed["task_total_provider_cost_micros"])

    # -- 7. #609's precedence, frozen ---------------------------------------

    def _two_standing_lines(self):
        """The seat's own line (3,000,000 / 3,200,000) and then the
        business's (4,500,000 / 5,000,000), both standing."""
        self._a_pooled_business_with_two_seats()
        self._default_pool(3_000_000)
        self._pool_line(self.biz, cap=5_000_000, pct=90)
        self._report(self.seat1, bills=3_200_000)
        self._drain()
        self._report(self.seat1, bills=1_800_000)

    def test_a_business_stop_named_over_the_seats_replays_the_business_stop(self):
        key = self._key()
        self._two_standing_lines()
        original = self._report(self.seat1, idempotency_key=key)
        self._assert_stopped(original, reasons.CUSTOMER_SPEND_POOL, "customer",
                             TRIGGER_SOURCE_USAGE_INGEST,
                             bound=4_500_000, measured=5_000_000)
        # The business's line clears; the seat's own is now the one named.
        self._put_pool(self.biz, cap=100_000_000, pct=100)
        self._clear_the_owner_level(self.biz)
        self._assert_stopped(self._report(self.seat1),
                             reasons.CUSTOMER_SPEND_POOL, "customer",
                             TRIGGER_SOURCE_USAGE_INGEST,
                             bound=3_000_000, measured=3_200_000)

        self._assert_replayed(self._report(self.seat1, idempotency_key=key),
                              original)

    def test_a_seats_own_stop_replays_as_the_seats_after_the_business_stops(self):
        key = self._key()
        self._a_pooled_business_with_two_seats()
        self._default_pool(3_000_000)
        self._pool_line(self.biz, cap=5_000_000, pct=90)
        self._report(self.seat1, bills=3_200_000)
        self._drain()
        original = self._report(self.seat1, idempotency_key=key)
        self._assert_stopped(original, reasons.CUSTOMER_SPEND_POOL, "customer",
                             TRIGGER_SOURCE_USAGE_INGEST,
                             bound=3_000_000, measured=3_200_000)
        # The business's line opens; it is now the one named.
        self._assert_stopped(self._report(self.seat1, bills=1_800_000),
                             reasons.CUSTOMER_SPEND_POOL, "customer",
                             TRIGGER_SOURCE_USAGE_INGEST,
                             bound=4_500_000, measured=5_001_000)

        self._assert_replayed(self._report(self.seat1, idempotency_key=key),
                              original)


class AReplayOnTheSingleRouteTest(AReplayAnswersWhatTheAcknowledgementSaid,
                                  ThroughTheSingleRoute, PoolTestBase):
    pass


class AReplayOnABatchItemTest(AReplayAnswersWhatTheAcknowledgementSaid,
                              ThroughABatchItem, PoolTestBase):
    pass


class AKeyReplaysAcrossTheTwoRoutesTest(MovesTheLiveFactsOn, PoolTestBase):
    """4. A key first recorded on one route replays identically on the other.
    The single route's answer and a batch item's are one acknowledgement, so
    each case names both routes rather than binding one."""

    def _pins(self, first, then):
        self._pool_line(self.customer, cap=10_000_000, pct=80)
        key = f"idem-{uuid.uuid4()}"
        original = first(self.customer, bills=9_000_000, idempotency_key=key)
        self._put_pool(self.customer, cap=20_000_000, pct=50)
        replayed = then(self.customer, bills=9_000_000, idempotency_key=key)
        self.assertEqual(self._the_acknowledgement(replayed),
                         self._the_acknowledgement(original))
        self.assertEqual(replayed["stop_bound_micros"], 8_000_000)

    def _the_acknowledgement(self, body):
        """The single route's body, or a batch item less the three keys only
        a verdict has (`accepted`, and the rejection's `code` and `detail`,
        null on an accepted item)."""
        return {key: value for key, value in body.items()
                if key not in ("accepted", "code", "detail")}

    def test_a_key_first_recorded_in_a_batch_replays_identically_alone(self):
        self._pins(self._one_batch_item, self._record)

    def test_a_key_first_recorded_alone_replays_identically_in_a_batch(self):
        self._pins(self._record, self._one_batch_item)


class TheStopAcknowledgementIsKeptOnceTest(PoolTestBase):
    """The record's own rules: one per recorded result, written with its
    posting, insert-only at the database, and never reconstructed."""

    def _one_kept(self):
        self._record(bills=1_000)
        return StopAcknowledgement.objects.get()

    def _a_failing_recording(self, key):
        """POST one report the server cannot answer: the API renders the
        unhandled exception as a 500 and logs it. Returns the exception."""
        with self.assertLogs("api.v1.problems", level="ERROR") as logged:
            response = self.http.post(
                "/api/v1/metering/usage",
                data=json.dumps(self._usage(bills=1_000, idempotency_key=key)),
                **self._headers())
        self.assertEqual(response.status_code, 500, response.content)
        return logged.records[0].exc_info[1]

    def test_every_recorded_result_keeps_one_stopped_or_not(self):
        self._record(bills=1_000)
        batch = self.http.post("/api/v1/metering/usage/batch", data=json.dumps(
            {"events": [self._usage(bills=1_000), self._usage(bills=2_000)]}),
            **self._headers())
        self.assertEqual(batch.status_code, 200, batch.content)
        self.assertEqual(Posting.objects.count(), 3)
        self.assertEqual(
            set(StopAcknowledgement.objects.values_list("posting_id", flat=True)),
            set(Posting.objects.values_list("id", flat=True)))
        self.assertFalse(StopAcknowledgement.objects.filter(stop=True).exists())

    def test_a_tenant_that_does_not_enforce_keeps_an_unstopped_one(self):
        """Enforcement off reads no customer-wide stop at all — a flag left
        standing is not consulted — and the record still says so: stopped
        false, every fact null."""
        self.tenant.enforcement_mode = "off"
        self.tenant.save(update_fields=["enforcement_mode"])
        Door.plant_stop(self.customer.id, reasons.HARD_FLOOR)

        ack = self._record(bills=1_000)

        self.assertFalse(ack["stop"])
        kept = StopAcknowledgement.objects.get(posting_id=ack["event_id"])
        self.assertEqual(
            (kept.stop, kept.stop_reason, kept.trigger_source,
             kept.stop_bound_micros, kept.stop_measured_micros,
             kept.stop_customer_id),
            (False, None, None, None, None, None))

    def test_it_is_written_in_the_recording_transaction(self):
        """A failure keeping the record leaves no posting: the two commit
        together or not at all."""
        failing = mock.patch.object(
            StopAcknowledgement.objects, "create",
            side_effect=DatabaseError("the record could not be kept"))
        with failing:
            raised = self._a_failing_recording("kept-together")
        self.assertIsInstance(raised, DatabaseError)
        self.assertFalse(Posting.objects.filter(
            idempotency_key="kept-together").exists())

    def _around_the_guard_save(self, kept, **columns):
        """`save()`, reaching around the model's own refusal — what a writer
        bypassing the override looks like (`usage/tests/_helpers.through_save`):
        the plain `save()` raises before the database is asked anything, and
        would prove nothing about it."""
        for name, value in columns.items():
            setattr(kept, name, value)
        models.Model.save(kept)

    def test_an_update_is_refused_by_the_database_through_every_door(self):
        kept = self._one_kept()
        doors = {
            "save(), around the guard": lambda: self._around_the_guard_save(
                StopAcknowledgement.objects.get(id=kept.id), stop=True),
            "a queryset update": lambda: StopAcknowledgement.objects.filter(
                id=kept.id).update(stop_bound_micros=1),
            "raw SQL": lambda: connection.cursor().execute(
                "UPDATE ubb_stop_acknowledgement SET stop = true WHERE id = %s",
                [kept.id]),
        }
        for door, write in doors.items():
            with self.subTest(door=door):
                with self.assertRaisesRegex(IntegrityError, "insert-only"), \
                        transaction.atomic():
                    write()
        kept.refresh_from_db()
        self.assertFalse(kept.stop)
        self.assertIsNone(kept.stop_bound_micros)
        # The model's own door is shut too (not the enforcement).
        with self.assertRaises(ValueError):
            kept.save()

    def test_a_delete_is_refused_by_the_database_through_every_door(self):
        kept = self._one_kept()
        doors = {
            "delete(), around the guard": lambda: models.Model.delete(
                StopAcknowledgement.objects.get(id=kept.id)),
            "a queryset delete": lambda: StopAcknowledgement.objects.filter(
                id=kept.id).delete(),
            "raw SQL": lambda: connection.cursor().execute(
                "DELETE FROM ubb_stop_acknowledgement WHERE id = %s",
                [kept.id]),
        }
        for door, write in doors.items():
            with self.subTest(door=door):
                with self.assertRaisesRegex(IntegrityError, "insert-only"), \
                        transaction.atomic():
                    write()
        self.assertTrue(StopAcknowledgement.objects.filter(id=kept.id).exists())
        with self.assertRaises(ValueError):
            kept.delete()

    def test_the_rule_fires_before_each_update_and_delete_and_never_on_insert(self):
        """`BEFORE UPDATE OR DELETE ... FOR EACH ROW`, read out of `tgtype`'s
        bits. The INSERT bit being OFF is the load-bearing half: the
        migration's cost argument is that the recording path's one insert per
        recorded result never enters the function (`django-patterns.md`: a
        rule asserts its statement mask rather than describing it)."""
        tgtype, _ = rule_on_the_table("trg_stop_acknowledgement_is_insert_only",
                                      table="ubb_stop_acknowledgement")
        self.assertTrue(tgtype & (1 << 0), "not FOR EACH ROW")
        self.assertTrue(tgtype & (1 << 1), "not BEFORE")
        self.assertTrue(tgtype & (1 << 4), "does not fire on UPDATE")
        self.assertTrue(tgtype & (1 << 3), "does not fire on DELETE")
        self.assertFalse(tgtype & (1 << 2), "fires on INSERT")

    def test_a_sandbox_is_discarded_with_its_records(self):
        """The admitted move: a sandbox's reset discards its postings
        wholesale, and their records go with them (the measurement rule's
        own carve-out, #354)."""
        live = Tenant.objects.create(name="live")
        sandbox = Tenant.objects.create(name="live sandbox", is_sandbox=True,
                                        parent_tenant=live)
        customer = Customer.objects.create(tenant=sandbox, external_id="c1")
        posting = Posting.objects.create(tenant=sandbox, customer=customer,
                                         idempotency_key="k")
        StopAcknowledgement.objects.create(posting=posting, stop=False)

        Customer.all_objects.filter(id=customer.id).delete()

        self.assertFalse(StopAcknowledgement.objects.filter(
            posting_id=posting.id).exists())

    def test_a_recorded_posting_with_no_record_is_an_invariant_violation(self):
        """Never reconstructed from live facts: a recording-path posting the
        record is missing for raises a named error, on the service and on
        the route."""
        Posting.objects.create(tenant=self.tenant, customer=self.customer,
                               idempotency_key="no-record",
                               billing_owner_id=self.customer.id)

        with self.assertRaises(StopAcknowledgementMissing):
            UsageService.replay(self.tenant, self.customer, "no-record")
        self.assertIsInstance(self._a_failing_recording("no-record"),
                              StopAcknowledgementMissing)

    def test_a_key_a_charge_holds_is_refused_and_never_replayed(self):
        """A delivered fixed-price unit's Charge posting carries a key UBB
        derived (`task:<id>`) and no acknowledgement. A report sent under
        that key is refused before anything is recorded — never answered
        with the Charge's posting, and never the missing-record error."""
        TaskType.objects.create(tenant=self.tenant, key=SOLD_WHOLE,
                                kind=TASK_TYPE_KIND_TASK,
                                pricing_mode=PRICING_MODE_FIXED, uncapped=True)
        a_price_for_whole_work(self.tenant, task_type=SOLD_WHOLE,
                               amount_micros=THE_AGREED_PRICE)
        unit = self._unit(task_type=SOLD_WHOLE)
        with mock.patch(DOORBELL), self.captureOnCommitCallbacks(execute=True):
            closed = self.http.post(
                f"/api/v1/tasks/{unit}/close",
                data=json.dumps({"outcome": TASK_OUTCOME_DELIVERED}),
                **self._headers())
        self.assertEqual(closed.status_code, 200, closed.content)
        charge_key = Posting.objects.get(task_id=unit).idempotency_key

        alone = self.http.post(
            "/api/v1/metering/usage",
            data=json.dumps(self._usage(bills=1_000, idempotency_key=charge_key)),
            **self._headers())
        in_a_batch = self._one_batch_item(bills=1_000, idempotency_key=charge_key)

        self.assertEqual(alone.status_code, 422, alone.content)
        self.assertEqual(alone.json()["code"], "validation_error")
        self.assertIn("Charge", alone.json()["detail"])
        self.assertFalse(in_a_batch["accepted"])
        self.assertEqual(in_a_batch["code"], "validation_error")
        self.assertEqual(Posting.objects.filter(idempotency_key=charge_key).count(), 1)
