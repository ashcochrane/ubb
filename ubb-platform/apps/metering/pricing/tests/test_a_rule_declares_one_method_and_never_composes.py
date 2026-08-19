"""A pricing rule declares one method, and never composes (#355, #147 §2).

Two claims, and they fail for different reasons:

* **The method is one of exactly two, or nothing.** The set is the registry's
  (`domain-vocabulary/concepts/economics.yaml`), imported rather than typed
  here or in the model, so this table cannot hold a set the agreed model
  disagrees with. Null is not a third value: it says the price was not
  *derived*, and which of the two reasons for that — it was agreed, or there is
  none — is read off the price status beside the amount on the posting.
* **A rule carries no second component beside its METHOD.** A margin over
  supplier cost does not also carry a floor, a cap or an additive term. The
  reason is not aesthetic: each rule's output has to be independent of every
  other so a resolved price can be explained by naming ONE rule, and a
  composition model makes the explanation a chain whose middle terms nobody
  stored. ⚠ **That is not the whole of "rules never compose", and the class
  below says which half it holds** — a second composition is expressible on
  this table, belongs to the rule's ARITHMETIC SHAPE rather than to its method,
  and is deliberately left legal here.

**WHY BOTH ARE DRIVEN THROUGH THREE DOORS.** `choices=` reaches forms, the
admin and `full_clean`, and none of those is a constraint: `QuerySet.update()`
and raw SQL write straight past all three, which the cases below demonstrate
rather than assert. ADR-0007 §2 makes the same argument one field over, about
transitions — *"the database rejects forbidden transitions regardless of the
path"* — and a value set is the same kind of claim. A rule only one door
respects is the defect the rule exists to catch.

**AND WHY EVERY REFUSAL HERE ASSERTS ITS CONSTRAINT BY NAME.** MANY mechanisms
on this table answer `IntegrityError` — three checks, a partial unique index,
two triggers, every foreign key and every `NOT NULL` column — and no count of
them is worth writing down, because the number was already stale once in this
file's own history. "The write was rejected" stopped being evidence of anything
here several slices ago, and a test asserting only the exception type would
pass while the wrong mechanism did the refusing. The two checks this module is
about are told apart from EACH OTHER the same way, which is why
`RuleRefusalThroughEveryDoorMixin.REFUSAL_NAME` has no default.

**A REFUSAL IS PROVED BY AN ADMISSION BESIDE IT.** A check that refused every
write would satisfy every refusal below, so each pair of refusals is followed by
the writes that must still succeed — including the shape every rate on disk is
in today, which states no method at all.

**THE RETIRED WORDS THIS MODULE NEVER SPELLS.** The cost/price discriminator,
the container's pointer and the shape-of-charge column are names slice 4 owns
and whose ledger counts are ceilings as well as floors, so rules are built
through `_helpers.rate_in_default_book` — which carries the first for its
callers — and the other two are never passed, because the model's defaults are
already what every case here wants. The three write doors live beside that
helper because `docs/conventions/testing.md` puts shared test scaffolding
there, and the raw-SQL one addresses the table through `Rate._meta.db_table`
rather than by name — a name this slice is going to re-spell, so a reader that
goes through the model follows the rename instead of going quietly stale.
"""

from django.db import IntegrityError, models, transaction
from django.test import TestCase

from apps.metering.pricing.models import (
    DECLARES_A_RATIFIED_METHOD_CHECK,
    NEVER_COMPOSES_CHECK,
    Rate,
)
from apps.metering.pricing.tests._helpers import (
    RuleRefusalThroughEveryDoorMixin, rate_in_default_book)
from apps.platform.tenants.models import Tenant
from core.vocabulary import (
    PRICING_METHOD_DIRECT_EVENT_PRICE,
    PRICING_METHOD_MARGIN_OVER_COST,
    PRICING_METHOD_VALUES,
)

#: The column this module is about, spelled once.
METHOD = "pricing_method"

#: A value no registry has ever declared. Deliberately plausible: a set closed
#: by a comment rather than by the database is closed against typos and open to
#: anything a caller means sincerely.
A_METHOD_NOBODY_RATIFIED = "cost_plus_fixed_fee"


def _tenant(name="T"):
    return Tenant.objects.create(name=name, default_currency="usd")



class APricingRuleDeclaresOneOfTwoRatifiedMethodsTest(
        RuleRefusalThroughEveryDoorMixin, TestCase):
    """The value set, closed at the table rather than in a comment."""

    REFUSAL_NAME = DECLARES_A_RATIFIED_METHOD_CHECK

    def setUp(self):
        self.tenant = _tenant()

    def test_the_column_offers_the_registry_s_two_values_and_no_others(self):
        """AC: the two ratified values, IMPORTED — no hand-written list.

        Read off the field rather than off the module constant beside it,
        because what a `CharField` was handed is the thing a form, the admin and
        `full_clean` will act on, and a constant nothing was built from would
        agree with the registry while the column did not.
        """
        offered = {value for value, _ in
                   Rate._meta.get_field(METHOD).choices}

        self.assertEqual(offered, set(PRICING_METHOD_VALUES))
        self.assertEqual(len(offered), 2)

    def test_a_rule_may_declare_either_of_them(self):
        """The admission the refusals below are measured against."""
        for method in sorted(PRICING_METHOD_VALUES):
            with self.subTest(method=method):
                rule = rate_in_default_book(
                    self.tenant, measurement_key=f"q_{method}",
                    pricing_method=method,
                    rate_per_unit_micros=0, fixed_micros=0)

                rule.refresh_from_db()
                self.assertEqual(getattr(rule, METHOD), method)

    def test_a_rule_may_state_no_method_at_all(self):
        """Null is admitted, and it is the shape every rule on disk is in.

        Null is not a third value and the check says so positively: a membership
        test answers NULL for a NULL column, which a check reads as satisfied,
        so admitting it is a decision rather than an oversight.
        """
        rule = rate_in_default_book(self.tenant, measurement_key="q_null")

        rule.refresh_from_db()
        self.assertIsNone(getattr(rule, METHOD))

    def test_a_third_method_cannot_be_inserted(self):
        """The INSERT door — the one a check holds and a `BEFORE UPDATE`
        trigger never sees."""
        with self.assertRaisesRegex(IntegrityError,
                                    DECLARES_A_RATIFIED_METHOD_CHECK):
            with transaction.atomic():
                rate_in_default_book(
                    self.tenant, measurement_key="q_third",
                    pricing_method=A_METHOD_NOBODY_RATIFIED)

    def test_a_third_method_cannot_be_written_over_an_existing_rule(self):
        """The three update doors, each going further round the model."""
        rule = rate_in_default_book(self.tenant, measurement_key="q_update")

        self.assert_every_door_refuses(
            rule, pricing_method=A_METHOD_NOBODY_RATIFIED)
        self.assertIsNone(getattr(rule, METHOD))


class ARuleCarriesNoSecondComponentBesideItsMethodTest(
        RuleRefusalThroughEveryDoorMixin, TestCase):
    """Non-composition, as a property of a row rather than a sentence.

    ⚠ **THIS HOLDS COMPOSITION *BESIDE A METHOD*, AND TWO OTHER PARTS OF "RULES
    NEVER COMPOSE" ARE NOT HELD HERE. Both are named, because a module that
    claimed the whole property while enforcing a third of it would be worse
    than one that claimed nothing.**

    1. **Refused here.** A `margin_over_cost` rule carrying either component
       this table can express — the per-unit rate, or the flat addend beside it.
       Those are the OTHER method's terms, so carrying them is a second
       component bolted to a margin.
    2. **Not expressible here at all.** The mirror: a direct rule carrying a
       margin term. No percentage column exists on this table while markup is
       still a separate record, so there is nothing to refuse. The ticket that
       moves markup onto the rule is the ticket that adds it.
    3. **Expressible and deliberately left legal.** A rule may carry BOTH money
       terms at once, and `Rate.compute` adds them — so one rule can be a
       per-unit charge plus a flat addend. That is a composition, and it is a
       fact about the rule's ARITHMETIC SHAPE rather than about which method
       derived the price: the shape's two alternatives are per-unit and a
       component that applies once, and whether they may be mixed is decided
       with the shape's own rename. Refusing it here would change what an
       existing rate may be, in a ticket that renames nothing and whose
       migration must apply against a populated table.

    `test_the_direct_method_carries_its_own_terms_and_is_admitted` below is the
    admission that pins (3) as a decision rather than an oversight.
    """

    REFUSAL_NAME = NEVER_COMPOSES_CHECK

    def setUp(self):
        self.tenant = _tenant()

    def test_a_margin_rule_cannot_be_inserted_carrying_a_per_unit_term(self):
        with self.assertRaisesRegex(IntegrityError, NEVER_COMPOSES_CHECK):
            with transaction.atomic():
                rate_in_default_book(
                    self.tenant, measurement_key="q_per_unit",
                    pricing_method=PRICING_METHOD_MARGIN_OVER_COST,
                    rate_per_unit_micros=1_000)

    def test_a_margin_rule_cannot_be_inserted_carrying_an_additive_term(self):
        with self.assertRaisesRegex(IntegrityError, NEVER_COMPOSES_CHECK):
            with transaction.atomic():
                rate_in_default_book(
                    self.tenant, measurement_key="q_additive",
                    pricing_method=PRICING_METHOD_MARGIN_OVER_COST,
                    fixed_micros=250)

    def test_a_second_component_cannot_be_added_to_a_margin_rule_later(self):
        """The composition a check written only over INSERT would have missed:
        a rule declared clean, then given a term afterwards."""
        rule = rate_in_default_book(
            self.tenant, measurement_key="q_later",
            pricing_method=PRICING_METHOD_MARGIN_OVER_COST,
            rate_per_unit_micros=0, fixed_micros=0)

        self.assert_every_door_refuses(rule, fixed_micros=250)
        self.assert_every_door_refuses(rule, rate_per_unit_micros=1_000)
        self.assertEqual(rule.fixed_micros, 0)
        self.assertEqual(rule.rate_per_unit_micros, 0)

    def test_a_method_cannot_be_declared_over_a_rule_that_already_composes(self):
        """The same defect arriving from the other side, which is the one a
        rule written only over the money columns would have let through: the
        terms are already there and the method is declared afterwards."""
        rule = rate_in_default_book(
            self.tenant, measurement_key="q_reverse",
            rate_per_unit_micros=1_000, fixed_micros=250)

        self.assert_every_door_refuses(
            rule, pricing_method=PRICING_METHOD_MARGIN_OVER_COST)
        self.assertIsNone(getattr(rule, METHOD))

    def test_a_margin_rule_with_neither_term_is_admitted(self):
        """The admission that makes the four refusals above mean something."""
        rule = rate_in_default_book(
            self.tenant, measurement_key="q_margin_alone",
            pricing_method=PRICING_METHOD_MARGIN_OVER_COST,
            rate_per_unit_micros=0, fixed_micros=0)

        rule.refresh_from_db()
        self.assertEqual(getattr(rule, METHOD), PRICING_METHOD_MARGIN_OVER_COST)

    def test_the_direct_method_carries_its_own_terms_and_is_admitted(self):
        """The point of the asymmetry: these terms are not a SECOND component
        for a rule whose method is the one they belong to."""
        rule = rate_in_default_book(
            self.tenant, measurement_key="q_direct",
            pricing_method=PRICING_METHOD_DIRECT_EVENT_PRICE,
            rate_per_unit_micros=1_000, fixed_micros=250)

        rule.refresh_from_db()
        self.assertEqual(getattr(rule, METHOD),
                         PRICING_METHOD_DIRECT_EVENT_PRICE)
        self.assertEqual(rule.rate_per_unit_micros, 1_000)

    def test_a_rule_stating_no_method_keeps_every_term_it_has_today(self):
        """Every rule on disk is in this shape, and none of them may break.

        The check has to be satisfied by a null method whatever else the row
        carries, or the migration that installed it would have been unable to
        apply against a populated table.
        """
        rule = rate_in_default_book(
            self.tenant, measurement_key="q_untouched",
            rate_per_unit_micros=1_000, fixed_micros=250)

        rule.refresh_from_db()
        self.assertIsNone(getattr(rule, METHOD))
        self.assertEqual(rule.fixed_micros, 250)


class ARuleHasNowhereToHideAFloorOrACapTest(TestCase):
    """The other half of non-composition: there is no column for one.

    A refusal over the two terms that exist says nothing about a THIRD arriving
    later under a name that reads like a rounding rule. What holds that is the
    pinned set below — a floor, a cap or a second addend would be a whole-number
    column on this model and would move it, which puts it in front of a reader
    in the commit that adds it.

    ⚠ **IT KEYS ON `IntegerField`, NOT ON `BigIntegerField`, AND THE DIFFERENCE
    IS THE WHOLE GUARD.** The three money terms happen to be big integers and
    the two book bounds beside them are not, which is the proof that a
    whole-number column here need NOT be big: keyed on the narrower class,
    `floor_micros = models.PositiveIntegerField()` would sail straight past the
    check whose docstring says it would be caught. `BigIntegerField` and
    `PositiveIntegerField` are both `IntegerField` subclasses, so the wider key
    is the one that actually holds the claim.

    That the set includes two columns which are not terms is not a weakness of
    it: what this pins is *which whole-number columns exist*, and naming the
    two non-terms explicitly is what stops a reader thinking the omission of a
    third was deliberate.
    """

    #: Every whole-number column the rule carries — the three money terms, and
    #: the two bounds saying which versions of its book the rule belongs to.
    #: Read off the model rather than listed twice: a hand-written list would go
    #: on agreeing with itself while the model moved underneath it.
    WHOLE_NUMBER_COLUMNS = {
        "rate_per_unit_micros", "unit_quantity", "fixed_micros",
        "book_version_from", "book_version_to",
    }

    def test_the_rule_carries_exactly_these_whole_number_columns(self):
        present = {field.name for field in Rate._meta.concrete_fields
                   if isinstance(field, models.IntegerField)}

        self.assertEqual(present, self.WHOLE_NUMBER_COLUMNS)


class NoThirdOrFourthMethodExistsAnywhereTest(TestCase):
    """AC: two values, and the places a third could hide.

    The pricing-versions decision's receipt shape lists FOUR — the two below
    plus a fixed-task-price value and an explicit `none` — and the registry is
    the oracle (ADR-0008 §2). Neither dropped value loses a distinction: `none`
    is the ABSENCE of a method, which the nullable column and the price status
    beside it already say; and a fixed task price is the whole-job regime, a
    concept of its own that the receipt snapshots by value.

    The contract's own half of this claim — that the published `enum` carries
    these two and nothing else — is asserted in the contract suite at the git
    root, where the document and the registry are compared. It is not restated
    here, because a second copy of it would agree with this one rather than with
    the shipped bytes.
    """

    def test_the_generated_value_set_holds_exactly_the_two(self):
        self.assertEqual(set(PRICING_METHOD_VALUES),
                         {PRICING_METHOD_MARGIN_OVER_COST,
                          PRICING_METHOD_DIRECT_EVENT_PRICE})

    def test_the_absence_of_a_method_is_a_null_and_not_a_value(self):
        """The distinction the fourth value would have blurred."""
        self.assertTrue(Rate._meta.get_field(METHOD).null)
        self.assertNotIn(None, {value for value, _ in
                                Rate._meta.get_field(METHOD).choices})
