"""A supplier-cost total and the count of what it left out, built together.

`Posting.provider_cost_micros` is nullable, and `NULL` means **UBB has not
resolved this cost** (#317, ADR-0007 §2). Zero keeps a meaning of its own —
resolved, and it was exactly nothing. That distinction is held at the database,
and this module is what stops it being thrown away one step later.

**SQL's aggregates skip `NULL`.** A bare ``Sum("provider_cost_micros")``
therefore answers a number that looks complete and is not, and it does so
silently: nothing in the result says how many rows it passed over. That is not
SQL being wrong — it is the answer being **undeclared**. So every supplier-cost
total UBB reports is a **pair**:

* the **resolved sum** — every cost UBB holds, added up
* the **count of postings excluded from it** — every cost UBB has not learned

and the pair is built by the two functions below so that a reader cannot take
one without the other. ``carry_cost_total`` writes both keys or neither.

**Why ``or 0`` is not the fix, and is deleted rather than moved.** It produces a
figure *indistinguishable from a complete one*, which is the exact ambiguity the
nullable column just stopped having — the defect wearing a better hat (#146 §4).
The only place a `NULL` sum becomes a zero here is
:func:`cost_total`, and there it is the **empty sum**: no row contributed, so
the total is nothing, and the count travelling beside it is what says whether
that nothing is *"nothing was spent"* or *"nothing is known"*. Before the pair
those two answered the same 0. They no longer do, and
``api/v1/tests/test_a_cost_total_says_what_it_excluded.py`` holds them apart.

**What the count counts, and what it deliberately does not.**
``not_applicable`` also carries a `NULL` amount and is also skipped by SQL — but
nothing about it is missing. The Event Type declares no supplier cost, so the
cost is genuinely zero and the total is genuinely complete. Counting it would
mark every metering-only tenant's every total partial forever, and a caveat
that is always on is a caveat nobody reads. The count is of ``unresolved``
alone.

**Anything derived from a partial total is partial, and carries the same
count.** A margin over a cost total missing an event is a ceiling on a margin,
not a margin; a markup over one is a floor. There is one fact — which events
were excluded — and a total's own arithmetic does not make it two, so nothing
here mints a second counter for a derived figure.

This module is in the kernel because the sweep it serves crosses every product:
metering computes these totals, and billing, subscriptions, platform and
referrals read them through the read contracts. ADR-001 allows every product to
import ``core.*``; a helper living in metering would have been reachable by
nobody who needs it.
"""
from django.db.models import Count, Q, Sum

from core.vocabulary import COSTING_STATUS_UNRESOLVED

#: What a cost total calls the count of postings it could not include. One
#: spelling, because the value crosses four products and a per-product literal
#: is how four products come to disagree about the same fact.
UNRESOLVED_EVENT_COUNT_KEY = "unresolved_event_count"

#: The posting's columns, named once. They are public because the GATE reads
#: them: `apps/platform/tests/test_no_bare_supplier_cost_aggregate.py` walks the
#: tree for a `Sum` over the first of these, and asks HERE which column that is
#: rather than holding a copy of the name — a gate naming its own subject is a
#: gate that expires silently the day the column is renamed.
#:
#: They are constants rather than parameters of the functions below because
#: exactly one table carries this pair. When a second one does — slice 4's
#: billed cost is the candidate — that is the commit that finds out what the
#: two tables have in common, and a knob added ahead of it would only be a guess
#: about the answer.
SUPPLIER_COST_COLUMN = "provider_cost_micros"
COSTING_STATUS_COLUMN = "costing_status"


def cost_total_annotations(*, key: str) -> dict:
    """The two expressions a supplier-cost aggregation takes, in one dict.

    Splat into ``.aggregate()`` or into ``.annotate()`` after a ``.values()``:
    the sum lands under ``key`` and its completeness under
    :data:`UNRESOLVED_EVENT_COUNT_KEY`, in the SAME query, so a grouped rollup
    cannot end up counting one group's exclusions against another's total.

    The count is a filtered ``Count`` rather than a second query for the same
    reason.
    """
    return {
        key: Sum(SUPPLIER_COST_COLUMN),
        UNRESOLVED_EVENT_COUNT_KEY: Count(
            "id", filter=Q(**{COSTING_STATUS_COLUMN: COSTING_STATUS_UNRESOLVED})),
    }


def cost_total(*, key: str, resolved_micros: int | None,
               unresolved_events: int) -> dict:
    """The pair, as data: the resolved sum under ``key`` and its completeness.

    ``resolved_micros`` is `None` when **no row contributed** — an empty window,
    or a window in which every cost is unresolved. That is the empty sum, and it
    is nothing; ``unresolved_events`` is what tells the two apart. See the module
    docstring for why this is not the ``or 0`` this ticket deleted everywhere
    else.

    Available to a caller that accumulates in Python rather than in SQL, so that
    a product carrying the pair through does not have to invent its own shape
    for it.
    """
    return {
        key: 0 if resolved_micros is None else resolved_micros,
        UNRESOLVED_EVENT_COUNT_KEY: unresolved_events,
    }


def carry_cost_total(row: dict, *, key: str) -> dict:
    """Resolve one aggregate row's pair IN PLACE, and return the row.

    ``row`` is what a ``cost_total_annotations`` block produced — an
    ``.aggregate()`` result or one row of a grouped ``.annotate()``. Both keys
    are already present and both are rewritten, so a row that has been through
    this function is safe to return to a caller as it stands.
    """
    row.update(cost_total(
        key=key, resolved_micros=row[key],
        unresolved_events=row[UNRESOLVED_EVENT_COUNT_KEY]))
    return row
