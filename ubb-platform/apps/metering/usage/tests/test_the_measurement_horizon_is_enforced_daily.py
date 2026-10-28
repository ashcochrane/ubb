"""The measurement horizon is enforced by a daily prune (#190 comment
5785029955; W5 rulings 7–11).

The published `measurement_data_available_from` is 400 days back by default.
`apps/metering/usage/pruning.py` releases and deletes the measurement records
older than it whose postings are resolved, a bounded batch at a time, once a day.
This module holds what the rulings require of that job:

- `prunable_at` is a SET_ONCE release fact, through `save()`, `QuerySet.update()`
  and raw SQL, and never a moment still to come;
- old, resolved records go; young records and the economic posting stay;
  unresolved and unknown ones stay and are counted as skipped in a stated scope;
- a re-run releases and deletes nothing more;
- an old unresolved record never starves younger eligible ones;
- batches and the run are bounded by two named numbers, and a capped run states
  its backlog;
- release and delete are one atomic unit: a batch whose delete fails leaves no
  record marked released;
- every run, a zero run included, writes one structured log line;
- the daily schedule runs it.

Every case states the clock it reads: the horizon comes from the setting it
overrides, and "today" is passed in, so no case depends on the day it runs.
"""
from datetime import timedelta
from unittest import mock

from django.conf import settings
from django.db import IntegrityError, connection, migrations, transaction
from django.db.migrations.loader import MigrationLoader
from django.db.models import Q
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from apps.metering.usage import pruning
from apps.metering.usage.models import Posting, PostingMeasurement
from apps.metering.usage.tests._helpers import committed_posting
from core.amount_status_pairs import CUSTOMER_PRICE, SUPPLIER_COST
from core.retention import MEASUREMENT_RETENTION_DAYS_SETTING
from core.transitions import SET_ONCE
from core.vocabulary import UNRESOLVED_REASON_COST_RATE_MISSING

DAYS = 400
HORIZON = {MEASUREMENT_RETENTION_DAYS_SETTING: DAYS}
SET_ONCE_TOKEN = "prunable_at is declared set_once"


def _measured(key, *, days_old, recorded_days_old=None, **posting_columns):
    """A posting and its measurement record, `days_old` before now.

    The event and its recording are the same age unless a case says otherwise,
    because the release reads both.
    """
    now = timezone.now()
    posting = committed_posting(idempotency_key=key,
                                effective_at=now - timedelta(days=days_old),
                                **posting_columns)
    recorded = days_old if recorded_days_old is None else recorded_days_old
    return PostingMeasurement.objects.create(
        posting=posting, measurements={"input_tokens": "7"},
        recorded_at=now - timedelta(days=recorded))


def _unresolved_cost(key, **kwargs):
    return _measured(key, provider_cost_micros=None,
                     costing_status=SUPPLIER_COST.unresolved_status,
                     unresolved_reason=UNRESOLVED_REASON_COST_RATE_MISSING,
                     **kwargs)


def _unknown_price(key, **kwargs):
    return _measured(key, billed_cost_micros=None,
                     pricing_status=CUSTOMER_PRICE.unresolved_status, **kwargs)


def _left(*measurements):
    return set(PostingMeasurement.objects.filter(
        pk__in=[m.pk for m in measurements]).values_list("pk", flat=True))


def _prune(**kwargs):
    return pruning.prune_measurements(today=timezone.now().date(), **kwargs)


# --- the release is SET_ONCE --------------------------------------------------

def _through_save(measurement, value):
    measurement.prunable_at = value
    measurement.save()


def _through_the_queryset(measurement, value):
    PostingMeasurement.objects.filter(pk=measurement.pk).update(prunable_at=value)


def _through_raw_sql(measurement, value):
    with connection.cursor() as cursor:
        cursor.execute(
            f"UPDATE {PostingMeasurement._meta.db_table} "
            f"SET prunable_at = %s WHERE id = %s", [value, measurement.pk])


DOORS = (_through_save, _through_the_queryset, _through_raw_sql)


class TheReleaseIsSetOnceTest(TestCase):
    """`prunable_at` is NULL until a record is released, then the instant it
    was, once (ruling 8), whichever door writes it."""

    def test_it_is_declared_set_once(self):
        self.assertEqual(PostingMeasurement.transition_classes["prunable_at"],
                         SET_ONCE)

    def test_null_to_a_past_instant_is_admitted_through_every_door(self):
        for door in DOORS:
            with self.subTest(door=door.__name__):
                measurement = _measured(f"admit-{door.__name__}", days_old=1)
                released = timezone.now() - timedelta(days=1)
                door(measurement, released)
                measurement.refresh_from_db()
                self.assertEqual(measurement.prunable_at, released)

    def _refused(self, door, measurement, value):
        with self.assertRaises(IntegrityError) as refusal:
            with transaction.atomic():
                door(measurement, value)
        self.assertIn(SET_ONCE_TOKEN, str(refusal.exception))

    def test_a_release_is_never_moved_through_any_door(self):
        for door in DOORS:
            with self.subTest(door=door.__name__):
                measurement = _measured(f"move-{door.__name__}", days_old=1)
                _through_the_queryset(measurement,
                                      timezone.now() - timedelta(days=2))
                measurement.refresh_from_db()
                self._refused(door, measurement,
                              timezone.now() - timedelta(days=5))

    def test_a_release_is_never_withdrawn_through_any_door(self):
        for door in DOORS:
            with self.subTest(door=door.__name__):
                measurement = _measured(f"withdraw-{door.__name__}", days_old=1)
                _through_the_queryset(measurement,
                                      timezone.now() - timedelta(days=2))
                measurement.refresh_from_db()
                self._refused(door, measurement, None)

    def test_a_release_is_never_a_moment_still_to_come(self):
        """A release in the future would be a deadline wearing the column —
        exactly what ruling 8 says it is not."""
        for door in DOORS:
            with self.subTest(door=door.__name__):
                measurement = _measured(f"future-{door.__name__}", days_old=1)
                self._refused(door, measurement,
                              timezone.now() + timedelta(days=30))
                measurement.refresh_from_db()
                self.assertIsNone(measurement.prunable_at)

    def test_recording_leaves_it_null(self):
        """Never a frozen deadline stamped at recording (ruling 8)."""
        self.assertIsNone(_measured("fresh", days_old=0).prunable_at)

    def test_the_rule_is_a_trigger_whose_reverse_is_exercised(self):
        """Forward and back against the real table, asserted by behaviour:
        with the rule out a release can be moved, and with it back it cannot."""
        migration = MigrationLoader(connection).get_migration(
            "usage", "0052_a_measurement_is_released_once_by_the_prune")
        run_python = next(op for op in migration.operations
                          if isinstance(op, migrations.RunPython))
        measurement = _measured("reverse", days_old=1)
        _through_the_queryset(measurement, timezone.now() - timedelta(days=2))

        with connection.schema_editor() as editor:
            run_python.reverse_code(None, editor)
        _through_the_queryset(measurement, timezone.now() - timedelta(days=3))

        with connection.schema_editor() as editor:
            run_python.code(None, editor)
        measurement.refresh_from_db()
        self._refused(_through_the_queryset, measurement,
                      timezone.now() - timedelta(days=4))


# --- what the prune takes, and what it leaves ---------------------------------

@override_settings(**HORIZON)
class ThePruneReleasesWhatTheHorizonNoLongerCoversTest(TestCase):

    def setUp(self):
        self.old = _measured("old", days_old=DAYS + 30)
        self.young = _measured("young", days_old=DAYS - 30)
        self.unresolved = _unresolved_cost("unresolved", days_old=DAYS + 60)
        self.unknown = _unknown_price("unknown", days_old=DAYS + 60)

    def test_an_old_resolved_record_goes_and_the_rest_stay(self):
        result = _prune()

        self.assertEqual(_left(self.old, self.young, self.unresolved,
                               self.unknown),
                         {self.young.pk, self.unresolved.pk, self.unknown.pk})
        self.assertEqual((result.released, result.deleted, result.skipped),
                         (1, 1, 2))
        self.assertFalse(result.capped)
        self.assertIsNone(result.oldest_remaining_eligible)
        self.assertIsNone(result.failed)

    def test_the_economic_posting_is_never_touched(self):
        """The economic clock is six years and this job never reads it
        (ruling 11): the posting whose detail went is the row it was before."""
        row = Posting.objects.filter(pk=self.old.posting_id)
        before = row.values().get()

        _prune()

        self.assertEqual(row.values().get(), before)

    def test_a_rerun_releases_and_deletes_nothing_more(self):
        _prune()
        again = _prune()

        self.assertEqual((again.released, again.deleted), (0, 0))
        self.assertEqual(again.skipped, 2)
        self.assertEqual(PostingMeasurement.objects.count(), 3)

    def test_the_horizon_is_the_one_configured_now(self):
        """The CURRENT clock decides (ruling 8): shorten it and the young record
        is releasable on the next run, with nothing stamped on it before."""
        with override_settings(**{MEASUREMENT_RETENTION_DAYS_SETTING: 30}):
            result = _prune()

        self.assertEqual(result.deleted, 2)
        self.assertEqual(_left(self.old, self.young), set())

    def test_an_event_or_a_recording_inside_the_horizon_keeps_its_detail(self):
        """Both the event and its recording must be older than the horizon: a
        back-dated recording of an old event keeps its detail for a full clock
        after it arrived, and so does a record of a recent event."""
        backdated = _measured("backdated", days_old=DAYS + 30,
                              recorded_days_old=DAYS - 30)
        late = _measured("late", days_old=DAYS - 30, recorded_days_old=DAYS + 30)

        result = _prune()

        self.assertEqual(_left(backdated, late), {backdated.pk, late.pk})
        # Skipped is what the walk REACHED and left: the late one, recorded
        # before the horizon, beside the two unresolved ones; the back-dated
        # one was recorded inside the horizon, so the walk never reached it.
        self.assertEqual(result.skipped, 3)


@override_settings(**HORIZON)
class AnOldUnresolvedRecordNeverStarvesYoungerOnesTest(TestCase):
    """Ruling 9: protected records are filtered by the query, never left for the
    delete trigger to refuse, so however many are older, the batch is filled
    from records that may go."""

    def test_the_oldest_record_being_unresolved_does_not_stop_the_rest(self):
        oldest = _unresolved_cost("oldest", days_old=DAYS + 300)
        eligible = [_measured(f"e{n}", days_old=DAYS + 100 - n)
                    for n in range(5)]

        first = _prune(batch_size=2, run_cap=2)
        second = _prune(batch_size=2, run_cap=10)

        self.assertEqual((first.deleted, second.deleted), (2, 3))
        self.assertEqual(_left(oldest, *eligible), {oldest.pk})

    def test_the_trigger_is_not_the_filter(self):
        """With the query's filter gone, the protected record is selected and
        the database refuses the batch — so the filter is what lets the job
        work, and the trigger is the backstop beneath it."""
        _unresolved_cost("protected", days_old=DAYS + 300)
        _measured("eligible", days_old=DAYS + 100)

        with mock.patch.object(pruning, "_protected", lambda: Q(pk__in=[])):
            with self.assertRaises(IntegrityError):
                _prune()


@override_settings(**HORIZON)
class TheRunIsBoundedAndSaysWhatItLeftTest(TestCase):

    def test_the_two_bounds_are_named_numbers(self):
        """Ruling 10: 1,000 per batch, and one named run cap."""
        self.assertEqual(pruning.PRUNE_BATCH_SIZE, 1_000)
        self.assertEqual(pruning.PRUNE_RUN_CAP, 100_000)
        defaults = pruning.prune_measurements.__kwdefaults__
        self.assertEqual(defaults["batch_size"], pruning.PRUNE_BATCH_SIZE)
        self.assertEqual(defaults["run_cap"], pruning.PRUNE_RUN_CAP)

    def test_no_batch_is_larger_than_the_batch_size(self):
        for n in range(5):
            _measured(f"m{n}", days_old=DAYS + 10 + n)
        sizes = []
        real = pruning._release_and_delete

        def counting(ids):
            sizes.append(len(ids))
            return real(ids)

        with mock.patch.object(pruning, "_release_and_delete", counting):
            result = _prune(batch_size=2)

        self.assertEqual(sizes, [2, 2, 1])
        self.assertEqual(result.deleted, 5)

    def test_a_capped_run_stops_at_the_cap_and_names_its_backlog(self):
        rows = [_measured(f"m{n}", days_old=DAYS + 50 - n) for n in range(5)]

        result = _prune(batch_size=2, run_cap=3)

        self.assertEqual(result.deleted, 3)
        self.assertTrue(result.capped)
        # The three oldest went; the oldest left is the backlog.
        self.assertEqual(_left(*rows), {rows[3].pk, rows[4].pk})
        self.assertEqual(result.oldest_remaining_eligible, rows[3].recorded_at)

    def test_a_capped_run_counts_only_the_protected_rows_it_walked_past(self):
        """The skipped count's scope (ruling 9): the rows the selection walked,
        never the whole older table."""
        _measured("first", days_old=DAYS + 100)
        _unresolved_cost("walked-past", days_old=DAYS + 90)
        _measured("second", days_old=DAYS + 80)
        _unresolved_cost("not-reached", days_old=DAYS + 70)
        _measured("third", days_old=DAYS + 60)

        capped = _prune(run_cap=2)
        finished = _prune()

        self.assertEqual((capped.deleted, capped.skipped), (2, 1))
        self.assertEqual((finished.deleted, finished.skipped), (1, 2))


@override_settings(**HORIZON)
class ReleaseAndDeleteAreOneUnitTest(TransactionTestCase):
    """Ruling 8: a batch whose delete fails leaves nothing marked released.

    ⚠ A `TransactionTestCase`, in autocommit, on purpose: inside a test's own
    transaction a failed statement aborts everything after it, so a batch that
    was NOT one unit would fail this for a different reason than the one it
    names. Here a release written outside the unit would be committed, and
    read back.
    """

    def test_a_failed_delete_rolls_the_batch_release_back(self):
        eligible = _measured("eligible", days_old=DAYS + 100)
        protected = _unresolved_cost("protected", days_old=DAYS + 200)

        # Plant the failure at the database: with the filter gone the batch
        # holds a record the delete trigger refuses, after the release ran.
        with mock.patch.object(pruning, "_protected", lambda: Q(pk__in=[])):
            with self.assertRaises(IntegrityError):
                _prune()

        self.assertEqual(
            set(PostingMeasurement.objects.filter(
                pk__in=[eligible.pk, protected.pk]).values_list(
                    "pk", "prunable_at")),
            {(eligible.pk, None), (protected.pk, None)})


@override_settings(**HORIZON)
class EveryRunWritesOneStructuredLineTest(TestCase):

    def _logged(self, **kwargs):
        with mock.patch.object(pruning.logger, "info") as info:
            result = _prune(**kwargs)
        self.assertEqual(info.call_count, 1, info.call_args_list)
        (event,), extra = info.call_args
        self.assertEqual(event, pruning.PRUNE_LOG_EVENT)
        return result, extra["extra"]["data"]

    def test_a_run_with_nothing_to_do_still_says_so(self):
        result, data = self._logged()

        self.assertEqual((data["released"], data["deleted"], data["skipped"]),
                         (0, 0, 0))
        self.assertEqual(data["horizon"], result.horizon.isoformat())
        self.assertIsNone(data["oldest_remaining_eligible"])
        self.assertEqual((data["batch_size"], data["run_cap"]),
                         (pruning.PRUNE_BATCH_SIZE, pruning.PRUNE_RUN_CAP))

    def test_a_working_run_states_released_deleted_skipped_and_its_backlog(self):
        rows = [_measured(f"m{n}", days_old=DAYS + 50 - n) for n in range(3)]
        _unresolved_cost("held", days_old=DAYS + 90)

        _, data = self._logged(run_cap=2, batch_size=1)

        self.assertEqual((data["released"], data["deleted"], data["skipped"],
                          data["capped"]), (2, 2, 1, True))
        self.assertEqual(data["oldest_remaining_eligible"],
                         rows[2].recorded_at.isoformat())

    def test_a_failed_run_still_writes_its_one_line(self):
        _unresolved_cost("protected", days_old=DAYS + 200)
        with mock.patch.object(pruning, "_protected", lambda: Q(pk__in=[])):
            with mock.patch.object(pruning.logger, "info") as info:
                with self.assertRaises(IntegrityError):
                    _prune()
        self.assertEqual(info.call_count, 1)
        self.assertEqual(info.call_args.kwargs["extra"]["data"]["failed"],
                         "IntegrityError")


class TheJobRunsEveryDayTest(TestCase):

    TASK = "apps.metering.usage.tasks.prune_measurement_detail"

    def test_one_daily_entry_schedules_it(self):
        entries = [entry for entry in settings.CELERY_BEAT_SCHEDULE.values()
                   if entry["task"] == self.TASK]
        self.assertEqual(len(entries), 1, entries)
        schedule = entries[0]["schedule"]
        self.assertEqual((len(schedule.hour), len(schedule.minute)), (1, 1))
        self.assertEqual(len(schedule.day_of_month), 31)
        self.assertEqual(len(schedule.day_of_week), 7)

    @override_settings(**HORIZON)
    def test_the_task_runs_the_prune_and_answers_its_result(self):
        _measured("old", days_old=DAYS + 30)
        from apps.metering.usage.tasks import prune_measurement_detail

        answer = prune_measurement_detail()

        self.assertEqual((answer["released"], answer["deleted"]), (1, 1))
        self.assertIsInstance(answer["horizon"], str)
