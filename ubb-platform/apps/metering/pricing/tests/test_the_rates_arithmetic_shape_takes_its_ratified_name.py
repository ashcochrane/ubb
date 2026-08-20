"""The rate's arithmetic shape takes its ratified name, values included (#366).

The column saying HOW a rule computes — an amount for each unit of quantity, or
an amount that applies once regardless — sat one character from `pricing_mode`,
a declared concept about something else entirely: which pricing regime governs a
whole job. ADR-0006 §3 forbids two public terms that close together and calls
the pair a defect rather than a coincidence; #151 §13.2 ratified the replacement
and #154 §3.3 locked it. So this is a forced rename, and it is the rename ADR-
0006 §3 uses as its own worked example.

**THREE CLAIMS LIVE HERE AND THEY FAIL FOR DIFFERENT REASONS.**

* **The move is a rename and it carries its data.** ADR-0007 §1: `RenameField`,
  never `AddField` beside `RemoveField` — which would leave a column of the
  right name holding nothing, and every "does the new name exist" assertion
  green over the loss. The value conversion beside it is RUN here, forwards and
  backwards over real rows, rather than asserted to exist.
* **The compute path branches through the named shape.** Both branches, with the
  discriminator asserted beside the amount — because a fixed rule's per-unit
  term is usually zero, so the per-unit formula answers CORRECTLY for it by
  accident, and a one-branch test reads exactly like coverage.
* **The contract carries the final name and no second spelling.**

⚠⚠ **THE VALUE THIS RENAME CONVERTS WAS INVISIBLE TO EVERY MECHANICAL CHECK,
AND SAYING SO IS PART OF THE POINT.** The retired name of the COLUMN is swept:
it holds a migration-ledger seat, the sweep counts the files carrying it, and
the count reaching zero is what closes the entry. The retired VALUE is not. It
lives under `retired_senses` rather than `retired_aliases` in
`domain-vocabulary/concepts/retired.yaml`, because `values_list(..., flat=True)`
is Django's own keyword and appears about a hundred times in first-party code —
sweeping the bare token would condemn the ORM, and that debt is unpayable, which
would put "the ledger reaches zero" out of reach by construction. The decision
is right and it has a price: **a ticket that greps for a retired token finds the
column and never finds the branch.** It was found by reading `Rate.compute`.

**NEITHER RETIRED SPELLING IS WRITTEN IN THIS MODULE.** Both are read off the
rename migration — the column name off its `RenameField`, the value off the
constant the conversion converts from. A test module is a living surface, and
the ledger's counts are ceilings on SPREAD as much as floors, so spelling the
column here would re-open an extent this same commit takes to zero. Deriving it
costs one import and takes no seeding authorisation, which is #275's own
technique in `test_the_rates_quantity_name_takes_the_canonical_name.py`.
"""

import json
from functools import cache
from importlib import import_module

from django.core.exceptions import FieldDoesNotExist
from django.db import connection, migrations as operations
from django.db.migrations.loader import MigrationLoader
from django.test import SimpleTestCase, TestCase

from api.v1.openapi_export import GIT_ROOT
from apps.metering.pricing.models import Rate
from apps.metering.pricing.services.pricing_service import PricingService
from apps.metering.pricing.tests._helpers import (
    a_usage_event_subject, cost_rate_in_default_book)
from apps.platform.event_types.tests._helpers import declares_a_quantity
from apps.platform.tenants.models import Tenant
from core.vocabulary import (
    RATE_STRUCTURE_FIXED_COMPONENT,
    RATE_STRUCTURE_PER_UNIT,
    RATE_STRUCTURE_VALUES,
)

APP_LABEL = "pricing"
RENAME_MIGRATION = "0026_the_rates_arithmetic_shape_takes_its_ratified_name"

_MODULE = import_module(f"apps.metering.pricing.migrations.{RENAME_MIGRATION}")

#: The two column names, both read off the rename itself.
#:
#: Unpacked from a one-element tuple on purpose: a migration that ever grew a
#: second `RenameField` would make `next(...)` pick one silently, and every
#: assertion below would then be about a column nobody meant.
(_RENAME,) = tuple(op for op in _MODULE.Migration.operations
                   if isinstance(op, operations.RenameField))
RETIRED_COLUMN = _RENAME.old_name
CANONICAL_COLUMN = _RENAME.new_name

#: The retired VALUE, read off the conversion rather than typed. It costs the
#: sweep nothing — a retired sense is not sweep input — but a literal here would
#: be a second copy of the thing the migration is the authority on, and the day
#: they disagreed this module would assert the conversion did something it did
#: not do.
RETIRED_VALUE = _MODULE.THE_RETIRED_SENSE

#: The three published schemas the shape appears on — the write, the reprice and
#: the read. Named rather than discovered: a walk that found two would report
#: success just as loudly.
PUBLISHED_SCHEMAS = ("RateIn", "RateChangeIn", "RateOut")


@cache
def schemas():
    """The published contract's schema block."""
    return json.loads(
        (GIT_ROOT / "openapi" / "v1.json").read_text(encoding="utf-8")
    )["components"]["schemas"]


class TheMoveIsARenameTest(TestCase):
    """ADR-0007 §1, checked against the migration rather than the message."""

    def setUp(self):
        self.migration = MigrationLoader(connection).get_migration(
            APP_LABEL, RENAME_MIGRATION)

    def test_it_carries_no_add_plus_remove(self):
        """The failure this rule exists to stop leaves no trace afterwards.

        An `AddField` beside a `RemoveField` produces a column of the right name
        holding none of the data, and every other assertion in this module would
        pass over it — the new name exists, the contract publishes it, the model
        answers. Only the rows would be gone.

        NESTED OPERATIONS ARE WALKED, for the reason #275's twin gives: an
        operation carrying lists of its own could hide a field add from a check
        that reads only the top level.
        """
        for op in self._every_operation():
            with self.subTest(operation=type(op).__name__):
                self.assertNotIsInstance(
                    op, (operations.AddField, operations.RemoveField))

    def _every_operation(self):
        for op in self.migration.operations:
            yield op
            yield from getattr(op, "database_operations", ())
            yield from getattr(op, "state_operations", ())

    def test_it_renames_the_column_on_the_rate(self):
        self.assertEqual(_RENAME.model_name.lower(), Rate._meta.model_name)

    def test_it_is_the_rename_the_conversion_and_the_value_set_and_nothing_else(self):
        """The whole operation list, in order, because the ORDER is load-bearing.

        The conversion runs AFTER the rename: it addresses the column through
        the migration state's own model, and at that point the state carries the
        new name. Written the other way round it would raise rather than
        silently miss, but the list is pinned here so a later edit that reorders
        them is a decision somebody makes rather than one that happens.
        """
        self.assertEqual([type(op).__name__ for op in self.migration.operations],
                         ["RenameField", "RunPython", "AlterField"])

    def test_the_retired_name_is_gone_from_the_model(self):
        with self.assertRaises(FieldDoesNotExist):
            Rate._meta.get_field(RETIRED_COLUMN)

    def test_the_column_takes_its_value_set_from_the_registry(self):
        """The `choices=` are the registry's, not a hand-typed pair.

        A hand-typed list is correct on the day it is written and silently wrong
        the day `domain-vocabulary/` moves — and this column's whole defect was
        a name nobody had checked against the registry. Asserted as a SET, since
        the order is the generator's business and not this claim's.
        """
        field = Rate._meta.get_field(CANONICAL_COLUMN)
        self.assertEqual({value for value, _ in field.choices},
                         set(RATE_STRUCTURE_VALUES))
        self.assertEqual(field.get_default(), RATE_STRUCTURE_PER_UNIT)


class _LiveApps:
    """`apps.get_model`'s interface, answered with the live models.

    The migration's functions take the historical registry; a test driving them
    outside a migration run has to hand them something with the one method they
    use. Narrow on purpose — it answers for this app's one model and nothing
    else, so a conversion that started reaching for a second model fails here
    loudly instead of being handed a registry that quietly serves it.
    """

    def get_model(self, app_label, model_name):
        assert app_label == APP_LABEL, app_label
        assert model_name == "Rate", model_name
        return Rate


class TheConversionCarriesItsDataTest(TestCase):
    """The value move, RUN over real rows rather than asserted to exist.

    ADR-0007 §1 is about the column; this is the same claim about what the
    column HOLDS. A rename that carried every row and left them all saying a
    word that no longer means anything would satisfy every operation-list check
    in the class above while leaving `compute` unable to recognise its own
    fixed-component rules — which is not a failed migration but a WRONG PRICE,
    silently, on every such rule.

    Driven through the migration's own functions over the live table, so what is
    exercised is the code that will run rather than a restatement of it.
    """

    def setUp(self):
        self.tenant = Tenant.objects.create(name="T")
        # The historical model at this point in the migration history, which is
        # what the conversion is handed. `apps.get_model` is not available
        # outside a migration run, and the live model is the right stand-in
        # here: the conversion touches one column and the two agree about it.
        self.apps = _LiveApps()

    def _a_rule_saying(self, value):
        rate = cost_rate_in_default_book(
            self.tenant, measurement_key="input_tokens", fixed_micros=7_500)
        Rate.objects.filter(pk=rate.pk).update(**{CANONICAL_COLUMN: value})
        return rate

    def _shape_of(self, rate):
        return getattr(Rate.objects.get(pk=rate.pk), CANONICAL_COLUMN)

    def test_a_row_on_the_retired_value_arrives_on_the_ratified_one(self):
        rate = self._a_rule_saying(RETIRED_VALUE)

        _MODULE.to_the_ratified_value(self.apps, None)

        self.assertEqual(self._shape_of(rate), RATE_STRUCTURE_FIXED_COMPONENT)

    def test_the_other_value_is_left_exactly_where_it_was(self):
        """The half a conversion gets wrong by being too broad.

        An `update()` with no filter would move every row, so a per-unit rule
        would come out of the migration charging a fixed component — the same
        wrong price as the untouched case, arriving from the other direction.
        """
        rate = self._a_rule_saying(RATE_STRUCTURE_PER_UNIT)

        _MODULE.to_the_ratified_value(self.apps, None)

        self.assertEqual(self._shape_of(rate), RATE_STRUCTURE_PER_UNIT)

    def test_the_reverse_puts_the_row_back_where_the_old_code_reads_it(self):
        """RUN, not asserted to exist.

        A rollback that renamed the column back and left the values converted
        would land on rows the old `compute` cannot recognise: its branch tests
        for the retired value, finds the ratified one, and takes the per-unit
        path for a rule that charges once. An un-reversed data migration is
        worse than none precisely here.
        """
        rate = self._a_rule_saying(RATE_STRUCTURE_FIXED_COMPONENT)

        _MODULE.back_to_the_retired_sense(self.apps, None)

        self.assertEqual(self._shape_of(rate), RETIRED_VALUE)


class TheComputePathRunsThroughTheNamedShapeTest(TestCase):
    """THE BRANCH THE SWEEP COULD NOT FIND, asserted on both sides.

    `Rate.compute` is where the arithmetic shape stops being a label and starts
    deciding money: a fixed-component rule is its fixed term and nothing else,
    while a per-unit rule divides and then ADDS that same fixed term. The value
    it compared against was the retired sense — not sweep input, no ledger seat,
    invisible to every mechanical check this repository owns.

    ⚠ **BOTH BRANCHES, AND THE DISCRIMINATOR BESIDE THE AMOUNT.** A fixed rule's
    per-unit term is normally zero, so applying the per-unit formula to it
    divides nothing and the fixed term survives the addition — the wrong branch
    answers correctly, and a one-branch test reads exactly like coverage. The
    cases below are built so that each branch would give a DIFFERENT number if
    the other one ran.
    """

    def setUp(self):
        self.tenant = Tenant.objects.create(name="T")
        declares_a_quantity(self.tenant, "api_calls")

    def _rule(self, **fields):
        return Rate(tenant=self.tenant, **fields)

    def test_a_flat_per_event_charge_computes_through_the_named_shape(self):
        """The AC's own case: an amount that applies once, whatever was measured.

        The per-unit term is NON-ZERO here, which is what makes this discriminate
        rather than describe. Under the per-unit formula the same row would
        answer 7,500 + 9 * 1,000 = 16,500; the fixed component alone is 7,500,
        and the quantity is irrelevant to it — which is asserted by computing the
        same rule over two different quantities.
        """
        rule = self._rule(**{CANONICAL_COLUMN: RATE_STRUCTURE_FIXED_COMPONENT},
                          fixed_micros=7_500, rate_per_unit_micros=1_000,
                          unit_quantity=1)

        self.assertEqual(getattr(rule, CANONICAL_COLUMN),
                         RATE_STRUCTURE_FIXED_COMPONENT)
        self.assertEqual(rule.compute(9), 7_500)
        self.assertEqual(rule.compute(9_000_000), 7_500)

    def test_a_per_unit_charge_takes_the_other_branch(self):
        """The control, and it is not a formality.

        Without it the branch above is satisfied by a method that returned
        `fixed_micros` unconditionally — which would price every per-unit rule in
        the system at its addend and nothing else.
        """
        rule = self._rule(**{CANONICAL_COLUMN: RATE_STRUCTURE_PER_UNIT},
                          fixed_micros=7_500, rate_per_unit_micros=1_000,
                          unit_quantity=1)

        self.assertEqual(getattr(rule, CANONICAL_COLUMN), RATE_STRUCTURE_PER_UNIT)
        self.assertEqual(rule.compute(9), 7_500 + 9_000)

    def test_the_receipt_records_the_shape_under_the_column_name(self):
        """What a reader six years from now needs to redo the sum.

        The component key follows `Rate.STRUCTURE_COLUMN`, so the record and the
        column cannot be renamed apart — and the key is REQUIRED of a component
        now (`receipts.REQUIRED_COMPONENT_KEYS`), which it could not be while
        the word was retired and this module was not one of the files allowed to
        carry it.

        ⚠ The rule's per-unit term is NON-ZERO here for the reason the class
        docstring gives, and it was zero in the first draft: at zero, applying
        the per-unit formula to this rule divides nothing and the fixed term
        survives the addition, so the amount below would read 7,500 under either
        branch and would assert nothing about which one ran. Measured — with the
        branch forced to per-unit, this case stayed GREEN at zero and goes red
        at 1,000.
        """
        rate = cost_rate_in_default_book(
            self.tenant, measurement_key="api_calls", fixed_micros=7_500,
            rate_per_unit_micros=1_000, unit_quantity=1,
            **{CANONICAL_COLUMN: RATE_STRUCTURE_FIXED_COMPONENT})

        receipt = PricingService._compute(
            subject=a_usage_event_subject(), currency="usd",
            effective_at="2026-01-01T00:00:00+00:00",
            measurements={"api_calls": 9},
            caller_provider_cost=None,
            resolve_declaration=lambda: None,
            resolve_card=lambda kind, key: rate,
            resolve_markup=lambda: None)

        component, = receipt["costing"]["detail"]["components"]
        self.assertEqual(component[Rate.STRUCTURE_COLUMN],
                         RATE_STRUCTURE_FIXED_COMPONENT)
        self.assertEqual(component["micros"], 7_500)


class TheContractCarriesTheFinalNameTest(SimpleTestCase):
    """ADR-0007 §3: the final name, on the published document, in this slice.

    The sweep proves the retired word has left the contract. It cannot prove the
    canonical one arrived — a rename that dropped the property altogether would
    clear the extent just as cleanly, and every client generated from the
    document would silently stop being able to say which arithmetic a rule runs.
    """

    def test_every_published_schema_carries_the_canonical_property(self):
        for name in PUBLISHED_SCHEMAS:
            with self.subTest(schema=name):
                self.assertIn(CANONICAL_COLUMN, schemas()[name]["properties"])

    def test_no_published_schema_carries_the_retired_property(self):
        for name, schema in schemas().items():
            with self.subTest(schema=name):
                self.assertNotIn(RETIRED_COLUMN, schema.get("properties", {}))

    def test_the_publish_body_can_move_it(self):
        """The capability that arrived with the rename (#358's hand-forward).

        A publish could not state a rule's arithmetic shape at all while the
        column's name was retired: the retired spelling would have broken a
        ledger ceiling on a brand-new schema, and the canonical one would have
        published a field whose values were still the retired ones. Both were
        assigned to this commit by name. Until it landed, the only route to
        moving a rule's shape was the immediate reprice route the publish act
        replaces — so the day that route goes, the capability would have gone
        with it.
        """
        self.assertIn(CANONICAL_COLUMN,
                      schemas()["BookChangeIn"]["properties"])
        self.assertIn(CANONICAL_COLUMN,
                      schemas()["RuleTermsOut"]["properties"])
