"""What a posting can still say about its measurements (#271).

A posting whose measured quantities have been pruned reads exactly like one
that never had any: both answer an empty bag. An API consumer cannot tell them
apart, and a console that defaults on an empty bag renders the second — so a
payload that expired on schedule reaches an end customer as a confident "no
usage". This module is the difference, and #193 §E5 rules where it lives.

**Derived, never stored.** All three answers are computable from facts the row
already carries, so a column holding a fourth copy could only ever disagree with
them — ADR-0006 §4, where the wrong encoding is always the one nobody is looking
at. §4 permits a derived fact to be *served* read-only, and that is all that
happens here: these functions are called by the serialiser and by nothing that
writes. The absence of a writable column is not left to good intentions, it is
gate G10 (`apps/platform/tests/test_model_naming.py`), which walks every model
in the app registry and fails on a column by this name.

**The rule is the registry's, not this module's.** `measurements_status` in
`domain-vocabulary/concepts/economics.yaml` declares it as `value_semantics` —
two boolean inputs, one answer each, proved total and unambiguous by the
compiler that reads it. The registry's own generator renders that table as a
comment into `core/vocabulary.py` rather than as data, deliberately, so that a
consumer wanting to evaluate it reads the registry: what is below is the one
evaluation, in the one place the serialiser calls.

**The kind is the seam slice 5 replaces.** `not_applicable` belongs to a
synthetic charge posting — a Task sold for one agreed price, projected as a
posting with revenue and no supplier work behind it. There is no `kind` column
to read it from and there must not be one here: `usage_event_kind`'s backend
consumer is a G2 debt whose ledger entry names slice 5 as its owner, and slice 5
is the slice that builds the Charge such a posting is projected from. Until
then nothing in this repository projects one, so :func:`posting_kind` answers
`metered_usage` for every row — from one place, so that the day the column
arrives there is one line to change and one test that fails if it is missed.
"""

from core.vocabulary import (
    MEASUREMENTS_STATUS_AVAILABLE,
    MEASUREMENTS_STATUS_NOT_APPLICABLE,
    MEASUREMENTS_STATUS_PRUNED,
    USAGE_EVENT_KIND_METERED_USAGE,
    USAGE_EVENT_KIND_TASK_CHARGE,
)

from .models import PostingMeasurement


def posting_kind(posting):
    """Which kind of posting this is — `metered_usage` for every row today.

    Not a column read, and deliberately not one: see the module note above for
    why the discriminator belongs to slice 5. This is where that read lands
    when it exists, and the argument is taken now so that every caller is
    already written against the shape it will have.
    """
    return USAGE_EVENT_KIND_METERED_USAGE


def measurements_status(kind, *, measured):
    """The declared rule, evaluated.

    ``kind`` is the posting's own `usage_event_kind`; ``measured`` is the
    registry's `a_measurement_record_exists`. The kind is read FIRST and the
    record's presence is not consulted for a charge — §E4 makes the child
    absent by construction there, so a rule that looked would answer `pruned`
    for a posting whose detail no retention horizon ever governed.
    """
    if kind == USAGE_EVENT_KIND_TASK_CHARGE:
        return MEASUREMENTS_STATUS_NOT_APPLICABLE
    if measured:
        return MEASUREMENTS_STATUS_AVAILABLE
    return MEASUREMENTS_STATUS_PRUNED


def measurements_status_for(posting):
    """One posting's answer — what the detail response serves.

    Reads the child through the forward relation rather than by counting rows,
    so a caller that has already ``select_related("measurement")`` pays no
    second query; the detail endpoint does exactly that.
    """
    return measurements_status(posting_kind(posting),
                               measured=_has_measurement(posting))


def _has_measurement(posting):
    """Whether the child record is there, without creating one to find out."""
    try:
        posting.measurement
    except PostingMeasurement.DoesNotExist:
        return False
    return True
