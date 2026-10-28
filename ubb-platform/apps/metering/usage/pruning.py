"""THE MEASUREMENT PRUNE — the daily job that enforces the measurement horizon
(#190 comment 5785029955; W5 rulings 7–11).

UBB keeps the economics for six years and fine measurement detail on a shorter
platform clock, `UBB_MEASUREMENT_RETENTION_DAYS` (400 days by default:
`core/retention.py`). The API publishes that clock's horizon on every economic
answer as `measurement_data_available_from`. This job is what makes the
published horizon true: once a day it removes the measurement records older
than the horizon that nothing still needs. The economic records — postings,
receipts, statuses, amounts — are never touched here; their clock is six years
and nothing in this module reads it.

**What a measurement needs to be released.** All three, read at run time:

- it is older than the CURRENT horizon — both the event it measured
  (`Posting.effective_at`) and its recording (`recorded_at`) fall before the
  horizon day, so neither a back-dated recording nor a late one loses its
  detail early;
- its posting is economically resolved: neither an `unresolved` supplier cost
  nor an `unknown` customer price, because a resolution run still needs these
  quantities to cost or price the event;
- it is not already released for a moment still to come (nothing writes one;
  the database refuses it since W5).

⚠⚠ **PROTECTED ROWS ARE FILTERED OUT BY THE QUERY; THE TRIGGER IS NEVER THE
FILTER** (ruling 9). The `usage/0041` delete trigger refuses an unresolved
measurement, but a refusal aborts the whole statement, so leaning on it would
make one protected row fail every batch it sat in. Selecting only eligible rows
is also what keeps an old unresolved row from STARVING younger eligible rows:
the batch is filled from rows that can go, oldest first, however many protected
rows are older still. The trigger stays as the backstop beneath.

⚠⚠ **RELEASE AND DELETE ARE ONE ATOMIC UNIT PER BATCH** (ruling 8). A batch
writes `prunable_at` — the release fact, SET_ONCE and stamped with the
database's own clock so the delete trigger reads it as already passed — and
deletes exactly those rows, inside one transaction. If the delete fails, the
release rolls back with it: a row is never left marked released by a run that
did not remove it. `prunable_at` is when a measurement was RELEASED, never a
deadline stamped at recording (recording leaves it NULL).

**Bounded and observable** (ruling 10). `PRUNE_BATCH_SIZE` rows per atomic unit,
at most `PRUNE_RUN_CAP` rows per run, and one structured log line per run —
zero-work runs included — carrying what was released and deleted, what was
skipped and the backlog (see `PruneResult`). A backlog the run cap leaves is
caught up on the following days, and the log says how old its oldest row is.

**Retention cleanup and economic resolution stay separate** (amendment B). The
prune never resolves a cost or a price and never invents a release for a row
that is unresolved; it leaves such a row for as long as it stays unresolved.
"""
import logging
from datetime import date, datetime
from typing import NamedTuple, Optional

from django.db import transaction
from django.db.models import Q
from django.contrib.postgres.functions import TransactionNow
from django.utils import timezone

from core.retention import retention_horizons
from core.time_windows import utc_day_start
from core.vocabulary import COSTING_STATUS_UNRESOLVED, PRICING_STATUS_UNKNOWN

logger = logging.getLogger(__name__)

#: How many measurement records one atomic unit releases and deletes.
PRUNE_BATCH_SIZE = 1_000

#: THE RUN CAP — the most measurement records one daily run releases and
#: deletes (ruling 10: one named number, stated in the PR). A hundred batches:
#: a day's run stays a few minutes of short transactions at the volumes UBB is
#: built for, and a larger backlog — a first run, or a horizon shortened by
#: configuration — is caught up over the days that follow, visibly, because the
#: run's log carries the oldest eligible row it left behind.
PRUNE_RUN_CAP = 100_000

#: The one structured log line every run writes.
PRUNE_LOG_EVENT = "measurement_prune.completed"


class PruneResult(NamedTuple):
    """What one run did, as its log line states it.

    ``released`` and ``deleted`` count the same rows from the two halves of
    each atomic unit: ``released`` is how many had their release written by
    this run (a row an earlier writer had already released is deleted without
    a second release), ``deleted`` how many went.

    ⚠ **``skipped`` HAS ONE SCOPE, AND IT IS THE RANGE THIS RUN INSPECTED**
    (ruling 9): the measurements recorded before the horizon that the run's
    walk reached and left in place — those at or before the last row it
    deleted, or every one recorded before the horizon when the run cleared the
    whole backlog. They stayed because their posting is still unresolved or
    unknown, or because the event they measure is inside the horizon. It is
    counted off the walk's own index range and never joins the posting, so the
    count cannot make the job read more than the prune does (`_passed_over`).

    ``oldest_remaining_eligible`` is the backlog: the recording instant of the
    oldest row that could have gone and did not, because the run cap stopped
    the run. None when the run caught up.

    ⚠ **A FAILED RUN COUNTS NOTHING MORE** (``skipped`` and the backlog are
    None): its line states what it released and deleted before the failure and
    which error stopped it, and asks the database nothing else — a connection a
    failure left unusable must not swallow the error or the line.
    """
    horizon: date
    released: int
    deleted: int
    skipped: Optional[int]
    capped: bool
    oldest_remaining_eligible: Optional[datetime]
    failed: Optional[str] = None

    def as_data(self):
        """The result as plain data — the log line's and the task's."""
        return {**self._asdict(), "horizon": self.horizon.isoformat(),
                "oldest_remaining_eligible": (
                    self.oldest_remaining_eligible.isoformat()
                    if self.oldest_remaining_eligible else None)}


def _protected():
    """A measurement whose posting a resolution run still needs it for."""
    return (Q(posting__costing_status=COSTING_STATUS_UNRESOLVED)
            | Q(posting__pricing_status=PRICING_STATUS_UNKNOWN))


def _older_than(cutoff):
    from apps.metering.usage.models import PostingMeasurement

    return PostingMeasurement.objects.filter(recorded_at__lt=cutoff,
                                             posting__effective_at__lt=cutoff)


def _eligible(cutoff):
    """Every measurement this run may release and delete, oldest first."""
    return (_older_than(cutoff)
            .exclude(_protected())
            .filter(Q(prunable_at__isnull=True)
                    | Q(prunable_at__lte=TransactionNow()))
            .order_by("recorded_at", "id"))


def _release_and_delete(ids):
    """ONE atomic unit: write the release, then delete exactly those rows.

    The release is stamped with the TRANSACTION's instant (`TransactionNow()`,
    Postgres' `CURRENT_TIMESTAMP`), because both triggers on this table read
    `now()`, which is that same instant. Python's clock — or Django's `Now()`,
    which is `STATEMENT_TIMESTAMP()` — reads a moment after the transaction
    began, so its release would name a moment still to come and be refused.
    """
    from apps.metering.usage.models import PostingMeasurement

    with transaction.atomic():
        released = PostingMeasurement.objects.filter(
            id__in=ids, prunable_at__isnull=True).update(prunable_at=TransactionNow())
        deleted, _ = PostingMeasurement.objects.filter(id__in=ids).delete()
    return released, deleted


def prune_measurements(*, today=None, batch_size=PRUNE_BATCH_SIZE,
                       run_cap=PRUNE_RUN_CAP):
    """Release and delete the measurements the horizon no longer covers.

    Idempotent: a second run on the same day finds nothing left to release and
    deletes nothing. Writes one structured log line whatever happens — a run
    that does nothing says so, and a run that fails says how far it got before
    the failure is raised.
    """
    today = today or timezone.now().date()
    horizon = retention_horizons(today).measurement
    cutoff = utc_day_start(horizon)
    released = deleted = 0
    last = None
    failed = None
    capped = False
    try:
        while deleted < run_cap:
            batch = list(_eligible(cutoff).values_list("id", "recorded_at")
                         [:min(batch_size, run_cap - deleted)])
            if not batch:
                break
            got_released, got_deleted = _release_and_delete(
                [row_id for row_id, _ in batch])
            released += got_released
            deleted += got_deleted
            last = batch[-1]
        else:
            capped = True
    except Exception as error:
        failed = type(error).__name__
        raise
    finally:
        result = _the_result(horizon, cutoff, released, deleted, last,
                             capped, failed)
        logger.info(PRUNE_LOG_EVENT, extra={"data": {
            **result.as_data(), "batch_size": batch_size, "run_cap": run_cap}})
    return result


def _passed_over(cutoff, through=None):
    """The records the run's walk reached and LEFT, recorded before the horizon.

    The walk goes through `ix_measurement_recorded_at` in `(recorded_at, id)`
    order and deletes every eligible record it reaches, so whatever is still
    there in the range it covered is exactly what it skipped: a record whose
    posting is unresolved or unknown, or one measuring an event inside the
    horizon. With ``through`` — the `(id, recorded_at)` of the last record a run
    that stopped short deleted — the range ends there; without it the run
    cleared the backlog and the range is everything recorded before the horizon.

    ⚠ **COUNTED OFF THE INDEX ALONE, WITH NO JOIN TO THE POSTING** (ruling 9).
    Asking the posting WHY each one stayed would let the planner scan the
    six-year economic table for a prettier number; the range count reads only
    the records the walk itself read.
    """
    from apps.metering.usage.models import PostingMeasurement

    rows = PostingMeasurement.objects.filter(recorded_at__lt=cutoff)
    if through is not None:
        last_id, last_recorded_at = through
        rows = rows.filter(recorded_at__lte=last_recorded_at).exclude(
            recorded_at=last_recorded_at, id__gt=last_id)
    return rows


def _the_result(horizon, cutoff, released, deleted, last, capped, failed):
    if failed:
        return PruneResult(horizon=horizon, released=released, deleted=deleted,
                           skipped=None, capped=capped,
                           oldest_remaining_eligible=None, failed=failed)
    oldest = None
    if capped:
        # The run stopped short of the backlog: it inspected the rows up to
        # the last one it deleted, and the oldest eligible row left is the
        # backlog the next run starts from.
        passed_over = _passed_over(cutoff, last)
        oldest = _eligible(cutoff).values_list("recorded_at", flat=True).first()
    else:
        passed_over = _passed_over(cutoff)
    return PruneResult(horizon=horizon, released=released, deleted=deleted,
                       skipped=passed_over.count(), capped=capped,
                       oldest_remaining_eligible=oldest, failed=failed)
