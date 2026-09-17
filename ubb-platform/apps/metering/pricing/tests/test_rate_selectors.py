import pytest
from django.db import IntegrityError, models
from apps.platform.tenants.models import Tenant
from apps.platform.grouping_fields.models import SLOT_CHOICES
from apps.metering.pricing.models import Rate
from apps.metering.pricing.tests._helpers import cost_rate_in_default_book
from core.vocabulary import ANALYTICS_ROLLUP_VALUES

#: The four axes that are always present on a posting and are never declared by
#: a tenant. Spelled here because they are not in the slot vocabulary, which is
#: the same reason `Rate.SELECTORS` spells them.
#:
#: ⚠ **THIS IS A PIN, NOT A THIRD SOURCE OF TRUTH**, and the duplication is the
#: point: a regression test that imports its expected answer from the code it
#: is testing cannot fail. It is deliberately NOT
#: `grouping_fields.models.RESERVED_KEYS`, which is a different set — that one
#: carries `customer` as a fifth member, because a customer is a reserved
#: GROUPING key without being a rate selector.
RESERVED_AXES = ("provider", "event_type", "task_type", "subtask_type")


@pytest.mark.django_db
class TestRateSelectors:
    def _t(self):
        return Tenant.objects.create(name="T")

    def test_a_rate_selects_on_the_four_reserved_axes_and_ten_declared_slots(self):
        """WHAT A RATE SELECTS ON, PINNED AS A WHOLE SET (#504, slice 7).

        ⚠ **BOTH HALVES ARE LITERALS ON PURPOSE, AND THAT IS THE WHOLE POINT
        OF THE TEST.** An earlier revision compared the slot half against
        `SLOT_CHOICES` — the very thing `Rate.SELECTORS` is built from one
        import away — so that half restated the implementation and could not
        fail whatever happened to it. A regression pin has to say what the
        answer IS; deriving it from the code under test is how a control goes
        quiet instead of red.

        The agreement between the model and the registry is a DIFFERENT claim
        and is asserted separately below, where a literal would be wrong.
        """
        assert Rate.SELECTORS == RESERVED_AXES + (
            "grouping_field_1", "grouping_field_2", "grouping_field_3",
            "grouping_field_4", "grouping_field_5", "grouping_field_6",
            "grouping_field_7", "grouping_field_8", "grouping_field_9",
            "grouping_field_10")
        assert len(Rate.SELECTORS) == 14

    def test_the_slot_half_is_read_off_the_registry_rather_than_restated(self):
        """`Rate`'s OWN CLAIM ABOUT ITSELF, CHECKED.

        The model says the slot half is *"read off the registry rather than
        restated, so a rate cannot end up selecting on a different set of slots
        from the one a tenant can declare."* That is an agreement between two
        modules, so here — unlike the pin above — comparing against
        `SLOT_CHOICES` is the assertion rather than a tautology: the two are
        meant to be the same and the test fails if they ever are not.
        """
        assert Rate.SELECTORS[len(RESERVED_AXES):] == tuple(
            slot for slot, _ in SLOT_CHOICES)

    def test_no_column_on_a_rate_is_a_free_text_container(self):
        """THE RETIRED BAG IS GONE, MODEL-WIDE AND BY TYPE RATHER THAN BY NAME.

        The selector it replaced was a JSON bag matched by SUBSET, against the
        exact equality every column here uses — the two matching semantics
        `Rate`'s own comment says were one query's two different rules.

        ⚠ **MODEL-WIDE, NOT SELECTOR-WIDE, AND THE DIFFERENCE IS REAL.** The
        pair of assertions this replaced named the retired bag and its hash
        column and checked they were absent from `_meta.get_fields()` — a claim
        about the whole TABLE. Asking only about columns named in `SELECTORS`
        would be strictly weaker: a bag re-added as an ordinary column would
        pass, and could then be read by a resolver without ever being declared
        a selector. `Rate` carries no JSON column at all today, so the honest
        form of the old claim is that it carries none — which also catches a
        bag arriving under a word nobody has thought of yet.
        """
        bags = sorted(f.name for f in Rate._meta.get_fields()
                      if isinstance(f, models.JSONField))
        assert bags == [], (
            f"{bags} are JSON containers on a rate. A rate selects by exact "
            f"equality on scalar columns; a subset match over a bag is the "
            f"second matching semantic design D3 removed. If a JSON column is "
            f"genuinely needed for something that is NOT selection, name it "
            f"here deliberately rather than widening this to the selector set")

    def test_every_selector_resolves_to_a_real_column(self):
        """A SELECTOR THAT NAMES NOTHING PINS NOTHING.

        Separate from the pin above because it fails for a different reason and
        should say so: the set can be exactly right while one of its names has
        no column behind it, which is what a half-finished rename looks like.
        """
        fields = {f.name for f in Rate._meta.get_fields()}
        missing = [name for name in Rate.SELECTORS if name not in fields]
        assert missing == [], (
            f"{missing} are declared selectors with no column on the table")

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
