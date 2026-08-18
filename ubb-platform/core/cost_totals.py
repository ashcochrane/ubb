"""A total over an amount UBB may not have, and the count of what it left out.

An amount column that is nullable, with a status column beside it saying why the
amount is missing, is an **amount/status pair**. The posting carries two:
`provider_cost_micros` with `costing_status` (#317), and `billed_cost_micros`
with `pricing_status` (#351). In both, `NULL` means **UBB has not resolved this
amount** (ADR-0007 §2) and zero keeps a meaning of its own — resolved, and it
was exactly nothing. That distinction is held at the database, and this module
is what stops it being thrown away one step later.

**SQL's aggregates skip `NULL`.** A bare ``Sum("provider_cost_micros")``
therefore answers a number that looks complete and is not, and it does so
silently: nothing in the result says how many rows it passed over. That is not
SQL being wrong — it is the answer being **undeclared**. So every total over
such a pair is itself a **pair**:

* the **resolved sum** — every amount UBB holds, added up
* the **count of rows excluded from it** — every amount UBB has not learned

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

**Which pair is a parameter, and there is deliberately only one helper (#348,
#351).** All three rules below take an :class:`AmountStatusPair` the caller
hands in. They held one table's two column names as module constants for as
long as exactly one such pair existed; the second arrived in #351, and the
alternative to a parameter is a second parallel helper, which guarantees the
rules disagree. That is the failure :func:`counts_as_unresolved` below already
names for five readers of one rule — the same failure one level up, between the
rules rather than inside one.

⚠ **The third rule took no pair until #351, and the argument for that has
expired rather than been overruled.** #348 gave :func:`cost_total` none because
it is handed the two numbers the aggregation already produced and read no
column, so a parameter it never consulted would have been a claim it does not
make. It now consults one — **which key the count travels under** — because
that key belongs to the pair and not to this module: the supplier count and the
price count are about different sets of postings, and most queries here total
both pairs at once.

Which tables have a pair, and what each one's count is called, is stated in
:mod:`core.amount_status_pairs`, so that the rules name no table and adding a
table changes no rule.

This module is in the kernel because the sweep it serves crosses every product:
metering computes these totals, and billing, subscriptions, platform and
referrals read them through the read contracts. ADR-001 allows every product to
import ``core.*``; a helper living in metering would have been reachable by
nobody who needs it.
"""
from dataclasses import dataclass

from django.db.models import Count, Q, Sum

#: What the SUPPLIER-COST total calls the count of rows it could not include.
#: One spelling, because the value crosses four products and a per-product
#: literal is how four products come to disagree about the same fact.
UNRESOLVED_EVENT_COUNT_KEY = "unresolved_event_count"

#: What the CUSTOMER-PRICE total calls the same count (#351).
#:
#: ⚠ A SECOND KEY, AND IT IS NOT A SECOND SPELLING OF THE FIRST. The two counts
#: are about **different sets of postings** — a posting can carry a settled
#: supplier cost and a customer price UBB could not resolve, and the reverse —
#: and most of the queries below total both pairs in one statement. One shared
#: key there would not merely be ambiguous: the second annotation would
#: overwrite the first in the same `dict`, and a margin's two caveats would
#: silently become one number answering for both.
#:
#: So the key belongs to the PAIR rather than to this module, which is why it
#: is read off :attr:`AmountStatusPair.count_key` at every site that writes one
#: and never spelled at a call site.
UNPRICED_EVENT_COUNT_KEY = "unpriced_event_count"


@dataclass(frozen=True)
class AmountStatusPair:
    """One table's nullable amount column and the status column beside it.

    Not the *total* pair this module builds — that is a sum and a count. This
    is the pair of COLUMNS a total is taken over, plus the one status value
    meaning *UBB has not learned this amount*, which travels with the columns
    because the rules that read them are the rules that need it, and a third
    argument threaded separately is a third thing that can disagree.

    A table's pair is declared once, in :mod:`core.amount_status_pairs`. The
    class is here rather than there because it is the shape the rules below are
    generic over, and a rules module that had to import the declarations to
    state its own signatures would still, transitively, name a table.
    """

    #: The nullable money column — what SQL sums and silently skips.
    amount_column: str
    #: The column that says WHY an amount is missing. An amount UBB has not
    #: learned and an amount that does not exist both carry `NULL`, so the
    #: amount can never tell them apart on its own.
    status_column: str
    #: The one value of :attr:`status_column` meaning UBB has not learned the
    #: amount — the rows a total's completeness count is about.
    unresolved_status: str
    #: What a total over this pair calls that count (#351). A property of the
    #: pair rather than of the rules, because two pairs are totalled in one
    #: query all over the read contract and a shared key would have the second
    #: annotation overwrite the first — one number answering for two different
    #: sets of excluded postings, with nothing raising.
    count_key: str


def counts_as_unresolved(pair: AmountStatusPair, status: str) -> bool:
    """Whether a row with no amount is one this count is ABOUT (#328).

    The module docstring's central ruling, as a function, because five readers
    accumulate in Python rather than in SQL and each of them had written the
    comparison out. For the supplier-cost pair, whose values name the rule:
    ``unresolved`` is a cost UBB has not learned and belongs in the count;
    ``not_applicable`` is a cost that does not exist and does not. Both carry a
    `NULL` amount, so the amount cannot tell them apart and every reader needs
    the status — which is why the value that means *not learned* is a property
    of the pair rather than a constant here.

    Named once because a rule restated in five places is a rule that will hold
    in four of them — and taking the pair rather than one table's status keeps
    that true for the second table instead of starting the count again. The SQL
    side never calls this: it filters on ``pair.unresolved_status`` inside
    :func:`cost_total_annotations`, which is the one other place the comparison
    is made and the reason this returns a bool rather than trying to serve both.
    """
    return status == pair.unresolved_status


def cost_total_annotations(pair: AmountStatusPair, *, key: str) -> dict:
    """The two expressions an aggregation over ``pair`` takes, in one dict.

    Splat into ``.aggregate()`` or into ``.annotate()`` after a ``.values()``:
    the sum lands under ``key`` and its completeness under ``pair.count_key``,
    in the SAME query, so a grouped rollup cannot end up counting one group's
    exclusions against another's total. Two pairs may be splatted into one
    query — that is the ordinary case in the read contract, which totals the
    supplier cost and the customer price together — and they do not collide
    because each writes its own count key.

    The count is a filtered ``Count`` rather than a second query for the same
    reason.

    ⚠ ``Count("id")`` is the one column name left in this module, and it is not
    the pair's — it is the primary key the rows are counted over, which every
    model here carries. A pair on a table keyed differently would have to
    parameterise that too, and nothing above would notice: the check in
    ``core/tests/test_cost_totals.py`` is about the PAIR's columns.
    """
    return {
        key: Sum(pair.amount_column),
        pair.count_key: Count(
            "id", filter=Q(**{pair.status_column: pair.unresolved_status})),
    }


def cost_total(pair: AmountStatusPair, *, key: str,
               resolved_micros: int | None, unresolved_events: int) -> dict:
    """The pair, as data: the resolved sum under ``key`` and its completeness.

    ``resolved_micros`` is `None` when **no row contributed** — an empty window,
    or a window in which every cost is unresolved. That is the empty sum, and it
    is nothing; ``unresolved_events`` is what tells the two apart. See the module
    docstring for why this is not the ``or 0`` this ticket deleted everywhere
    else.

    Available to a caller that accumulates in Python rather than in SQL, so that
    a product carrying the pair through does not have to invent its own shape
    for it.

    It takes the pair now (#351) where #348 deliberately gave it none. The
    argument then was that this rule reads no column, so a parameter it never
    consulted would be a claim it does not make. It consults one: which key the
    count travels under is the pair's, and a second pair arrived.
    """
    return {
        key: 0 if resolved_micros is None else resolved_micros,
        pair.count_key: unresolved_events,
    }


def carry_cost_total(pair: AmountStatusPair, row: dict, *, key: str) -> dict:
    """Resolve one aggregate row's pair IN PLACE, and return the row.

    ``row`` is what a ``cost_total_annotations`` block produced — an
    ``.aggregate()`` result or one row of a grouped ``.annotate()``. Both keys
    are already present and both are rewritten, so a row that has been through
    this function is safe to return to a caller as it stands.

    A row carrying TWO pairs is resolved by calling this once per pair: each
    call touches only its own two keys, and neither reads the other's.
    """
    row.update(cost_total(
        pair, key=key, resolved_micros=row[key],
        unresolved_events=row[pair.count_key]))
    return row
