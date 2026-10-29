"""The rate's arithmetic shape takes its ratified name, values included (#366).

The column saying HOW a rule computes — an amount for each unit of quantity, or
an amount that applies once regardless — sat one character from `pricing_mode`,
a declared concept about something else entirely: which pricing regime governs a
whole job. ADR-0006 §3 forbids two public terms that close together and calls
the pair a defect rather than a coincidence; #151 §13.2 ratified the replacement
and #154 §3.3 locked it. So this is a forced rename, and it is the rename ADR-
0006 §3 uses as its own worked example.

**THREE CLAIMS LIVE HERE AND THEY FAIL FOR DIFFERENT REASONS.**

* **The column carries the ratified name and the registry's value set.** Until
  the cutover (#190) this claim was also that the move was a rename carrying
  its data — ADR-0007 §1's `RenameField`, never `AddField` beside
  `RemoveField` — with the value conversion RUN forwards and backwards over
  real rows. The squash deleted that migration and every row in the old
  shape, so what is asserted now is the end state the rename produced.
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

**THE RETIRED COLUMN NAME IS NOT WRITTEN IN THIS MODULE.** It was read off the
rename migration's `RenameField` until the squash deleted it (#190); it is read
off the registry that retired it now (`rate_structure`'s `retired_aliases` in
`domain-vocabulary/concepts/economics.yaml`). A test module is a living
surface, and the ledger's counts are ceilings on SPREAD as much as floors, so
spelling the column here would re-open an extent that reached zero. Deriving
it costs one import and takes no seeding authorisation, which is #275's own
technique in `test_the_rates_quantity_name_takes_the_canonical_name.py`. The
retired VALUE was read off the conversion for the conversion's own tests, and
left with them.
"""

import json
from functools import cache

from django.core.exceptions import FieldDoesNotExist
from django.test import SimpleTestCase, TestCase

from api.v1.openapi_export import GIT_ROOT
from api.v1.tests._helpers import retired_aliases
from apps.metering.pricing.models import Rate
from apps.metering.pricing.services.pricing_service import PricingService
from apps.metering.pricing.tests._helpers import (
    a_usage_event_subject, cost_rate_in_default_book)
from apps.platform.event_types.tests._helpers import declares_a_quantity
from apps.platform.tenants.models import Tenant
from core.vocabulary import (
    PRICING_MODE_EVENT_PRICED,
    RATE_STRUCTURE_FIXED_COMPONENT,
    RATE_STRUCTURE_PER_UNIT,
    RATE_STRUCTURE_VALUES,
)

#: The canonical name — the model's own constant for its column, which the
#: receipt's component key follows too.
CANONICAL_COLUMN = Rate.STRUCTURE_COLUMN

#: The name it replaced, read off the registry: the concept retired exactly one
#: spelling, and the one-element unpack fails loudly if it ever lists another.
(RETIRED_COLUMN,) = retired_aliases("economics", CANONICAL_COLUMN)

#: The published schemas the shape appears on — the reprice and the read. Named
#: rather than discovered: a walk that found one would report success just as
#: loudly.
#:
#: ⚠ **THREE UNTIL #367, AND THE ONE THAT WENT WAS THE IMMEDIATE WRITE.** Adding
#: a rule is a declared change on a publish now, so the body that opened one
#: directly is deleted from the contract with its route, and #368 deleted the
#: immediate reprice body the same way. Their share of the claim did not vanish
#: with them: `BookRateChangeIn` carries the shape too, which #366 put there and
#: `tests/contracts/test_openapi_known_values.py` asserts by name over every
#: schema that carries a rule. This is the one this module's own subject — the
#: rate's SCHEMAS — still covers.
PUBLISHED_SCHEMAS = ("RateOut",)


@cache
def schemas():
    """The published contract's schema block."""
    return json.loads(
        (GIT_ROOT / "openapi" / "v1.json").read_text(encoding="utf-8")
    )["components"]["schemas"]


class TheColumnTakesItsRatifiedNameTest(TestCase):
    """ADR-0006 §3's worked example, asked of the model.

    Until the cutover (#190) this class also read `pricing/0026`'s operation
    list — a rename, a conversion and the value set, in that order — and a
    class beside it ran the conversion forwards and backwards over real rows.
    Those were claims about a migration the squash deleted, and about rows in a
    shape no database holds any more; what the rename produced is what is left.
    """

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
        self.assertEqual(rule.compute("9"), 7_500)
        self.assertEqual(rule.compute("9000000"), 7_500)

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
        self.assertEqual(rule.compute("9"), 7_500 + 9_000)

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
            measurements={"api_calls": "9"},
            caller_provider_cost=None,
            reported_cost_source_kind=None,
            # The ordinary regime and the ordinary posture (#418): this case is
            # about a COST component's arithmetic, and both facts decide only
            # whether a CUSTOMER price applies at all.
            pricing_mode=PRICING_MODE_EVENT_PRICED,
            # Names no Event Type, so no declaration is the rate path (#567)
            # rather than a hold (#568).
            names_an_event_type=False,
            resolve_declaration=lambda: None,
            resolve_the_cost_rule=lambda key: rate,
            resolve_the_price_rule=lambda key: None,
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
                      schemas()["BookRateChangeIn"]["properties"])
        self.assertIn(CANONICAL_COLUMN,
                      schemas()["RuleTermsOut"]["properties"])
