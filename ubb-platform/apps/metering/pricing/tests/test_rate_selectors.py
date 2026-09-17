import pytest
from django.db import models
from django.db import IntegrityError
from apps.platform.tenants.models import Tenant
from apps.platform.grouping_fields.models import SLOT_CHOICES
from apps.metering.pricing.models import Rate
from apps.metering.pricing.tests._helpers import cost_rate_in_default_book, rate_in_default_book
from core.vocabulary import ANALYTICS_ROLLUP_VALUES

#: The four axes that are always present on a posting and are never declared by
#: a tenant. Spelled here because they are not in the slot vocabulary, which is
#: the same reason `Rate.SELECTORS` spells them.
RESERVED_AXES = ("provider", "event_type", "task_type", "subtask_type")


@pytest.mark.django_db
class TestRateSelectors:
    def _t(self):
        return Tenant.objects.create(name="T")

    def test_a_rate_selects_on_the_four_reserved_axes_and_the_declared_slots(self):
        """WHAT A RATE SELECTS ON, ASSERTED AS A WHOLE SET (#504, slice 7).

        This replaced a pair of assertions naming the retired JSONB bag and its
        hash column, which said only that two spellings were absent. A set
        equality says the same thing and more: a column arriving under ANY new
        name fails here, which the name-by-name form could not catch, and the
        slot half is compared against the registry's own vocabulary rather than
        a literal, so the two cannot drift.
        """
        assert Rate.SELECTORS == RESERVED_AXES + tuple(
            slot for slot, _ in SLOT_CHOICES)

    def test_no_selector_is_a_free_text_container(self):
        """THE RETIRED BAG IS GONE, ASSERTED BY TYPE RATHER THAN BY ITS NAME.

        The selector it replaced was a JSON bag matched by subset, against the
        exact equality every column here uses — the two matching semantics
        `Rate`'s own comment says were one query's two different rules. Holding
        that to the TYPE rather than to the old spelling is what stops a bag
        returning under a word nobody has thought of yet.
        """
        fields = {f.name: f for f in Rate._meta.get_fields()}
        for name in Rate.SELECTORS:
            assert name in fields, (
                f"{name} is declared a selector and is not a column on the "
                f"table; a selector that resolves to nothing pins nothing")
            assert not isinstance(fields[name], models.JSONField), (
                f"{name} is a container; a rate selects by exact equality on a "
                f"scalar column, and a subset match is the semantic D3 removed")

    def test_no_reporting_rollup_is_a_rate_selector(self):
        """#145 §5 AND #147 §2 REMOVED THE REPORTING AXES FROM RATE SELECTION,
        AND SLICE 7 IS A VOCABULARY CHANGE RATHER THAN A READMISSION.

        The analytics rollups are read from the generated vocabulary, not
        spelled, so a rollup COINED later is covered by this test the day it
        lands. `assert ANALYTICS_ROLLUP_VALUES` is the vacuity guard: an empty
        set would make the loop below pass over nothing.
        """
        assert ANALYTICS_ROLLUP_VALUES
        for rollup in ANALYTICS_ROLLUP_VALUES:
            assert rollup not in Rate.SELECTORS, (
                f"{rollup} is a reporting rollup and may never select a rate")

    def test_specificity_counts_non_empty_selectors(self):
        t = self._t()
        r = cost_rate_in_default_book(t, provider="openai",
                                 event_type="chat", measurement_key="input_tokens",
                                 grouping_field_1="eu-west-1")
        assert r.specificity == 3

    def test_wildcard_rate_has_zero_specificity(self):
        t = self._t()
        r = cost_rate_in_default_book(t, measurement_key="input_tokens")
        assert r.specificity == 0

    def test_uniqueness_spans_all_selectors(self):
        t = self._t()
        cost_rate_in_default_book(t, provider="openai",
                             measurement_key="input_tokens", grouping_field_1="eu")
        # Same book, same quantity, DIFFERENT dim1 -> allowed.
        cost_rate_in_default_book(t, provider="openai",
                             measurement_key="input_tokens", grouping_field_1="us")
        assert Rate.objects.filter(measurement__code="input_tokens").count() == 2

    def test_duplicate_selector_set_is_rejected(self):
        t = self._t()
        cost_rate_in_default_book(t, provider="openai",
                             measurement_key="input_tokens", grouping_field_1="eu")
        with pytest.raises(IntegrityError):
            cost_rate_in_default_book(t, provider="openai",
                                 measurement_key="input_tokens", grouping_field_1="eu")
