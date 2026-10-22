"""Why a price does not apply: the regime decides, for every tenant (#351,
#151 §8.2; rewritten by #553, ADR-0021 §5).

The rule this file held until #553 was a tie-break between two reasons — a
metering-only tenant's fixed-price work recorded the tenant's posture
(`tenant_not_billing`, "posture wins") rather than the work's regime. The
owner's C2 ruling superseded it: whether UBB may know a customer's price is
not decided by whether UBB collects it, so the regime decides the reason and
the billing mode is not encoded again in the pricing result. The posture value
lost its last producer and was removed (`usage/0047`).

What is left is one fact and one answer, and the case where the fact is false
has no reason at all — the price applies. Both are asserted, and the posture is
asserted to be no input to the rule any more, which is what a regression to
the old tie-break would have to undo.

End to end, for both postures,
`api/v1/tests/test_the_postings_under_an_agreed_price_are_not_applicable.py`.
"""
import inspect

import pytest

from apps.metering.pricing.applicability import not_applicable_reason_for
from core.vocabulary import (
    NOT_APPLICABLE_REASON_FIXED_TASK_PRICING, NOT_APPLICABLE_REASON_VALUES)


@pytest.mark.parametrize("fixed_price, expected", [
    (True, NOT_APPLICABLE_REASON_FIXED_TASK_PRICING),
    # Not a `not_applicable` subject at all: the price applies.
    (False, None),
])
def test_the_reason_recorded_for_each_regime(fixed_price, expected):
    assert not_applicable_reason_for(
        sold_for_one_agreed_price=fixed_price) == expected


def test_the_tenants_posture_is_not_an_input_to_the_rule():
    """The C2 ruling, held at the rule's signature: there is no parameter
    through which a billing mode could reach the reason."""
    assert list(inspect.signature(not_applicable_reason_for).parameters) == [
        "sold_for_one_agreed_price"]


def test_every_reason_the_rule_can_answer_is_one_the_registry_holds():
    """And nothing the rule answers is outside the registry's set — the value
    that named the posture is gone from both."""
    answers = {not_applicable_reason_for(sold_for_one_agreed_price=fact)
               for fact in (True, False)} - {None}
    assert answers == NOT_APPLICABLE_REASON_VALUES


def test_the_fact_cannot_be_passed_positionally():
    """Keyword-only, so a call site says which fact it is passing."""
    with pytest.raises(TypeError):
        not_applicable_reason_for(True)
