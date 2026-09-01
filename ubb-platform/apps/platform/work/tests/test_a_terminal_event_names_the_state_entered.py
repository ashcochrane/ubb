"""The four terminal stop events, one per state a unit of work can be stopped
in, at each of the two altitudes (#140 §4.3, ratified in full by #154 §5.3).

Two events carried all four of these announcements until the split, named for a
BOUND — a state no unit of work is ever in — so an operator subscribed to spend
incidents was paged because a worker had crashed, and *how often did work stop
on a ceiling?* could not be answered without parsing a cause out of the
payload. The name now carries the state entered, and the cause and the
mechanism travel beside it as structured fields, so a subscriber classifies by
SUBSCRIBING rather than by parsing (ADR-0006 §5).

⚠ WHAT THESE FOUR CASES ARE FOR is the pairing, not any one name: `killed` and
`expired` are two different claims, and the whole value of the split is that a
subscriber can take one without the other. So the two lanes are driven at both
altitudes, and each case asserts the SET of terminal events that fired is
exactly its own — a single-event assertion would be satisfied by an emitter
that sent every name it knew.

The payload case beside them holds the OTHER half of §20's ruling: the two
OPEN vocabulary fields ship and the CLOSED control pair does not, because three
of that set's four families do not exist yet and publishing a closed set with
one producible member is the one thing a closed set may not do.
"""
import dataclasses

from apps.platform.events.schemas import (
    SubtaskExpired, SubtaskKilled, TaskExpired, TaskKilled)
from apps.platform.work import reasons
from apps.platform.work.tests._helpers import WorkTestBase
from core.vocabulary import (
    TASK_STATUS_EXPIRED, TASK_STATUS_KILLED, TRIGGER_SOURCE_STALE_REAPER,
    TRIGGER_SOURCE_USAGE_INGEST)
from apps.platform.work.services import TaskService


#: All four, so each case can rule out the other THREE rather than a chosen
#: one. Both mistakes the split exists to make impossible are in here: sending
#: the other STATE at this altitude, and sending this state at the other.
THE_FOUR = (TaskKilled, TaskExpired, SubtaskKilled, SubtaskExpired)


class ATerminalEventNamesTheStateEnteredTest(WorkTestBase):
    def _assert_announced(self, unit, event, *, status):
        """`unit` is in `status`, announced `event`, and announced NOTHING ELSE.

        The status is asserted beside the event because the two are one claim:
        the name IS the state entered, so a case that checked only the name
        would pass over an emitter that had stopped agreeing with the record.

        ⚠ THE ABSENCE IS ASSERTED OVER ALL FOUR, not over a chosen rival. A
        case ruling out only the other altitude would prove the containment
        rule and say nothing about the split itself — `subtask.killed` against
        `subtask.expired` is exactly the distinction this ticket exists to
        make, and it is the pair a subscriber alerting on spend subscribes
        across.
        """
        unit.refresh_from_db()
        self.assertEqual(unit.status, status)
        announcement = self._events(event.EVENT_TYPE).get()
        self.assertEqual(unit.announce_outbox_id, announcement.id)
        fired = {other.EVENT_TYPE for other in THE_FOUR
                 if self._events(other.EVENT_TYPE).exists()}
        self.assertEqual(fired, {event.EVENT_TYPE})
        return announcement

    def test_a_whole_unit_stopped_on_a_spend_signal_announces_task_killed(self):
        unit = self._task(limit=5_000_000)
        TaskService.kill_and_announce(
            unit.id, reasons.TASK_LIMIT, tenant_id=self.tenant.id,
            customer_id=self.customer.id,
            trigger_source=TRIGGER_SOURCE_USAGE_INGEST)

        self._assert_announced(unit, TaskKilled, status=TASK_STATUS_KILLED)

    def test_a_whole_unit_nobody_ever_closed_announces_task_expired(self):
        unit = self._task()
        TaskService.expire_and_announce(
            unit.id, reasons.SILENCE_WINDOW, tenant_id=self.tenant.id,
            customer_id=self.customer.id,
            trigger_source=TRIGGER_SOURCE_STALE_REAPER)

        self._assert_announced(unit, TaskExpired, status=TASK_STATUS_EXPIRED)

    def test_contained_work_stopped_on_a_spend_signal_announces_subtask_killed(
            self):
        parent, contained = self._a_parent_and_its_contained_work(
            limit=50_000_000)
        TaskService.kill_and_announce(
            contained.id, reasons.SUBTASK_LIMIT, tenant_id=self.tenant.id,
            customer_id=self.customer.id,
            trigger_source=TRIGGER_SOURCE_USAGE_INGEST)

        announcement = self._assert_announced(
            contained, SubtaskKilled, status=TASK_STATUS_KILLED)
        self.assertEqual(announcement.payload["parent_task_id"],
                         str(parent.id))
        # Contained work is stopped ALONE: the parent keeps running, so it has
        # nothing to announce and no stamp.
        parent.refresh_from_db()
        self.assertIsNone(parent.announce_outbox_id)

    def test_contained_work_nobody_ever_closed_announces_subtask_expired(self):
        parent, contained = self._a_parent_and_its_contained_work()
        TaskService.expire_and_announce(
            contained.id, reasons.SILENCE_WINDOW, tenant_id=self.tenant.id,
            customer_id=self.customer.id,
            trigger_source=TRIGGER_SOURCE_STALE_REAPER)

        announcement = self._assert_announced(
            contained, SubtaskExpired, status=TASK_STATUS_EXPIRED)
        self.assertEqual(announcement.payload["parent_task_id"],
                         str(parent.id))
        parent.refresh_from_db()
        self.assertIsNone(parent.announce_outbox_id)


class TheStoppedPayloadCarriesCauseAndMechanismTest(WorkTestBase):
    """§20's ruling, on the payload a subscriber actually receives."""

    def setUp(self):
        super().setUp()
        self.unit = self._task(limit=5_000_000)
        TaskService.kill_and_announce(
            self.unit.id, reasons.TASK_LIMIT, tenant_id=self.tenant.id,
            customer_id=self.customer.id,
            trigger_source=TRIGGER_SOURCE_USAGE_INGEST)
        self.payload = self._events(TaskKilled.EVENT_TYPE).get().payload

    def test_the_cause_and_the_mechanism_travel_as_two_fields(self):
        """Two questions — *why did this stop* and *what stopped it* — with two
        value sets, so two keys and never one. Asserted by constant identity;
        both words belong to vocabularies another slice owns.
        """
        self.assertEqual(self.payload["reason_code"], reasons.TASK_LIMIT)
        self.assertEqual(self.payload["trigger_source"],
                         TRIGGER_SOURCE_USAGE_INGEST)

    def test_the_payload_is_exactly_what_the_class_declares(self):
        """Held to the PRODUCER rather than to a written-out list, so a field
        added to (or dropped from) the frozen contract moves this case instead
        of quietly agreeing with a stale inventory."""
        self.assertEqual(
            set(self.payload),
            {field.name for field in dataclasses.fields(TaskKilled)})

    def test_it_carries_no_control_family_and_no_control_id(self):
        """§20's asymmetry, stated as a refusal rather than left to the set
        above: an OPEN vocabulary may ship with a subset of its known values by
        design, and a CLOSED one may not. Three of the four control families do
        not exist until spend control is rebuilt, so a payload advertising the
        set here would publish an enum UBB cannot fill. The slice that builds
        them adds an optional field, which is additive rather than a break.
        """
        self.assertNotIn("control_family", self.payload)
        self.assertNotIn("control_id", self.payload)

    def test_the_mechanism_is_recorded_on_the_row_the_announcement_names(self):
        """What #412 left for the split, in two places, so that the patrol's
        re-mint has something to read: the lane that APPLIES a stop is the only
        thing that knows which lane it is, and a repaired delivery names the
        same mechanism only if the applying lane wrote it down.
        """
        from apps.platform.work.services import STOP_MECHANISM_KEY

        self.unit.refresh_from_db()
        self.assertEqual(self.unit.metadata[STOP_MECHANISM_KEY],
                         TRIGGER_SOURCE_USAGE_INGEST)
