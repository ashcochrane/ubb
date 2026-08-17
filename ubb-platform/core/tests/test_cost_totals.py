"""The shared total answers for any amount/status pair, not for one table's (#348).

`core.cost_totals` holds three rules about an amount a column may not carry: the
coalescing rule, the unresolved-count rule, and the predicate that decides
whether a row with no amount is one the count is about. The two that read
columns — the count rule and the predicate — were welded to the posting's
supplier cost by two module constants until this commit, and the module said
why: *"exactly one table carries this pair"*. The coalescing rule reads no
column and never held one.

A second table is arriving, so the pair is a parameter and all three rules are
shared. **This module is the proof that the parameterisation is real**: every
rule is asked the same question about two different pairs, one of them the live
supplier-cost pair and one a fixture naming no column in this database. A
renamed constant would answer the fixture with the posting's columns and fail
here.

The behavioural assertions about supplier-cost totals — what the pair means to a
tenant reading a report — are not repeated here. They live at the surfaces that
publish them, in `api/v1/tests/test_a_cost_total_says_what_it_excluded.py` and
`api/v1/tests/test_four_products_carry_the_completeness_through.py`. This module
is about the seam alone, which is why it needs no database.
"""
import inspect

from django.db.models import Count, Q, Sum

from core import cost_totals
from core.amount_status_pairs import SUPPLIER_COST
from core.cost_totals import (
    UNRESOLVED_EVENT_COUNT_KEY, AmountStatusPair, carry_cost_total, cost_total,
    cost_total_annotations, counts_as_unresolved,
)
from core.vocabulary import (
    COSTING_STATUS_KNOWN, COSTING_STATUS_NOT_APPLICABLE,
    COSTING_STATUS_UNRESOLVED,
)

#: A pair that is not a column anywhere in this database, and deliberately so.
#: The second pair is what makes the parameterisation checkable before the
#: second real one exists, and a fictional one checks it harder than a real one
#: would: nothing about it can be supplied by an import the seam already has.
FIXTURE_PAIR = AmountStatusPair(
    amount_column="fixture_amount_micros",
    status_column="fixture_status",
    unresolved_status="fixture_unresolved",
)


def test_the_aggregation_names_the_pair_it_was_handed():
    """The unresolved-count rule, asked about two pairs.

    Asserted as the ORM expressions themselves rather than through a query,
    because the fixture pair has no table to query — which is the point of it.
    """
    assert cost_total_annotations(SUPPLIER_COST, key="total_micros") == {
        "total_micros": Sum("provider_cost_micros"),
        UNRESOLVED_EVENT_COUNT_KEY: Count(
            "id", filter=Q(costing_status=COSTING_STATUS_UNRESOLVED)),
    }
    assert cost_total_annotations(FIXTURE_PAIR, key="total_micros") == {
        "total_micros": Sum("fixture_amount_micros"),
        UNRESOLVED_EVENT_COUNT_KEY: Count(
            "id", filter=Q(fixture_status="fixture_unresolved")),
    }


def test_the_predicate_answers_for_the_pair_it_was_handed():
    """The unresolved predicate, asked about two pairs.

    The two crossed assertions are the ones that would survive a renamed
    constant and do not survive a real parameter: each pair's own unresolved
    value has to be the wrong answer for the other pair.
    """
    assert counts_as_unresolved(SUPPLIER_COST, COSTING_STATUS_UNRESOLVED) is True
    assert counts_as_unresolved(FIXTURE_PAIR, FIXTURE_PAIR.unresolved_status) is True

    assert counts_as_unresolved(SUPPLIER_COST, FIXTURE_PAIR.unresolved_status) is False
    assert counts_as_unresolved(FIXTURE_PAIR, COSTING_STATUS_UNRESOLVED) is False

    # The ruling the predicate exists for, unchanged: an amount that does not
    # exist is not an amount UBB failed to learn, and both carry `NULL`.
    assert counts_as_unresolved(SUPPLIER_COST, COSTING_STATUS_NOT_APPLICABLE) is False
    assert counts_as_unresolved(SUPPLIER_COST, COSTING_STATUS_KNOWN) is False


def test_the_coalescing_rule_is_one_rule_and_reads_no_column():
    """The empty sum is nothing, and which pair produced it changes nothing.

    `cost_total` takes no pair because it reads no column — it is handed the two
    numbers the aggregation already produced. That is the shape of the rule
    rather than an omission from the parameterisation: a parameter it never
    consulted would be a claim it does not make.
    """
    for key in ("provider_cost_micros", FIXTURE_PAIR.amount_column):
        assert cost_total(key=key, resolved_micros=None, unresolved_events=2) == {
            key: 0, UNRESOLVED_EVENT_COUNT_KEY: 2}
        assert cost_total(key=key, resolved_micros=7, unresolved_events=0) == {
            key: 7, UNRESOLVED_EVENT_COUNT_KEY: 0}


def test_a_row_is_resolved_in_place_whichever_pair_produced_it():
    for key in ("provider_cost_micros", FIXTURE_PAIR.amount_column):
        row = {key: None, UNRESOLVED_EVENT_COUNT_KEY: 3, "other": "untouched"}
        assert carry_cost_total(row, key=key) is row
        assert row == {key: 0, UNRESOLVED_EVENT_COUNT_KEY: 3, "other": "untouched"}


def test_the_helper_holds_no_column_of_its_own():
    """AC 1, as a check rather than as a sentence.

    The two constants this commit deleted are what made the seam one table's.
    Nothing stops a third being added next week for the same reason the first
    two were — so the absence is asserted rather than assumed, against the
    live pair's own column names so that renaming a column cannot make this
    test stop looking.
    """
    columns = (SUPPLIER_COST.amount_column, SUPPLIER_COST.status_column)
    held = {name for name, value in vars(cost_totals).items()
            if isinstance(value, str) and value in columns}
    assert held == set(), (
        f"core.cost_totals names a column again: {sorted(held)}. The pair is a "
        f"parameter — a table's columns belong in core.amount_status_pairs.")


def test_no_rule_can_be_called_without_saying_which_pair():
    """The re-weld the check above cannot see.

    A module-level constant is not the only road back. A DEFAULT —
    ``pair: AmountStatusPair = <the supplier-cost pair>`` — makes the argument
    optional and hands one table's answer to every caller who omits it, which
    is the old behaviour wearing a signature instead of a constant. `vars()`
    never sees a default, so the check above stays green through it.

    Importing the live pair to serve as that default is already impossible: it
    lives in a module that imports this one, so the cycle would refuse. A
    hand-built literal default would not be, and that is what this closes.
    """
    optional = []
    for name, fn in vars(cost_totals).items():
        if not inspect.isfunction(fn):
            continue
        parameter = inspect.signature(fn).parameters.get("pair")
        if parameter is not None and parameter.default is not inspect.Parameter.empty:
            optional.append(f"{name}(pair={parameter.default!r})")

    assert optional == [], (
        f"a rule can be called without naming its pair: {optional}. A default "
        f"is one table's answer, given to whoever does not ask.")
