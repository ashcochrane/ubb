"""The tie-break between the two `not_applicable_reason` values (#351, #151 §8.2).

Four combinations of two facts, and the whole content of the rule is the one row
where they disagree: a **metering-only tenant running a Task sold for one agreed
price** records `tenant_not_billing`, not `fixed_task_pricing`.

That row is why this file exists. The other three are obvious and would be
written by anybody; the tempting answer to the fourth is the more specific value,
and it is wrong — for a metering-only tenant no Charge is created anywhere, so
naming the job's regime would point a reader at revenue sitting on a Charge that
does not exist.

**Driven through the real function, table-first.** The rule is two branches, so a
test per branch would be a test per line of the implementation; what has content
here is the mapping, and it is asserted as one.
"""
import pytest

from apps.metering.pricing.applicability import not_applicable_reason_for
from core.vocabulary import (
    NOT_APPLICABLE_REASON_FIXED_TASK_PRICING,
    NOT_APPLICABLE_REASON_TENANT_NOT_BILLING,
)

#: (tenant bills through UBB, sold for one agreed price) -> reason.
#:
#: All four combinations, because a table missing one is a case somebody decides
#: later by accident. The `None` row is the case that has no reason at all.
THE_TIE_BREAK = [
    # The three rows of the ticket's table, in its order.
    (False, False, NOT_APPLICABLE_REASON_TENANT_NOT_BILLING),
    (True, True, NOT_APPLICABLE_REASON_FIXED_TASK_PRICING),
    (False, True, NOT_APPLICABLE_REASON_TENANT_NOT_BILLING),
    # And the fourth combination, which is not in that table because it is not a
    # `not_applicable` subject: the price applies.
    (True, False, None),
]


@pytest.mark.parametrize("bills, fixed_price, expected", THE_TIE_BREAK)
def test_the_reason_recorded_for_each_combination(bills, fixed_price, expected):
    assert not_applicable_reason_for(
        tenant_bills_through_ubb=bills,
        sold_for_one_agreed_price=fixed_price) == expected


def test_posture_beats_the_jobs_regime_where_they_disagree():
    """The one row above stated as its own claim, because it is the ruling.

    Asserted as an inequality against the value a caller would reach for, so
    that flipping the rule's two branches fails here with the reason named
    rather than only shifting one row of a parametrized table.
    """
    metering_only_fixed_job = not_applicable_reason_for(
        tenant_bills_through_ubb=False, sold_for_one_agreed_price=True)
    assert metering_only_fixed_job == NOT_APPLICABLE_REASON_TENANT_NOT_BILLING
    assert metering_only_fixed_job != NOT_APPLICABLE_REASON_FIXED_TASK_PRICING


def test_the_two_facts_cannot_be_passed_positionally():
    """Two booleans of the same type, and swapping them changes one answer.

    Keyword-only is the guard, and this is what proves it is still there: a
    positional call would be a silent wrong answer on exactly the row above.
    """
    with pytest.raises(TypeError):
        not_applicable_reason_for(False, True)
