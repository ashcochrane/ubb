"""No published schema names a physical slot (#277, ticket 20, AC 2).

This is an ABSENCE, and an absence is the claim that most easily passes for the
wrong reason — so it carries both halves of a vacuity guard: a positive control
proving the walk FAILS on a document that does expose a slot, and a pin on the
two schemas the ticket changed proving the walk read its actual subject.

**The positive half of the ticket is not here.** That a posting's grouping
values arrive keyed by the tenant's own declared key is proved end to end in
`test_usage_dimensions.py`, beside the write path they are declared through, and
the projection behind them in
`apps/metering/usage/tests/test_grouping_values_are_keyed_by_the_tenants_own_key.py`.

The round trip lives in an EXISTING file rather than a new one because posting
usage through the API means naming the declared-values request field and the
caller correlation identifier, whose words are both retired under other slices'
ledger entries. A new file naming them would push those recorded extents wider,
which the sweep refuses — a debt is a finite migration plan, not a licence for
the word to reach further while it stands. The projection file is new and
therefore names neither.
"""
import json
import re

from django.test import TestCase

from api.v1.openapi_export import COMMITTED_SPEC_PATH as COMMITTED

#: A property NAMED for a physical slot, in either spelling one has ever had.
#: `dim<n>` was the column name until #276 renamed the columns and deliberately
#: renamed no published property, so both spellings name the same thing — UBB's
#: internal identity for a binding the tenant knows by its own key.
#:
#: A property whose VALUE is a slot identifier is a different matter and is
#: deliberately not matched: `DimensionDefIn.slot` is how a tenant binds its key
#: to a slot in the first place, and the declaration surface is the one place
#: the physical slot is legitimately the subject.
SLOT_NAMED = re.compile(r"(dim|grouping_field_)\d+")

#: The published slot properties this ticket does NOT remove, and who does.
#:
#: The rate's selector list reaches the contract as six `dim<n>` properties.
#: Ticket 20's body is about a posting and says nothing about a rate, but its
#: acceptance criteria are worded wider — "no physical slot field is exposed on
#: any public schema" — so the scope is a real question rather than an oversight,
#: and #276 left it open in `schemas.py` for whoever got here first.
#:
#: **#193 §L answers it.** "The rate entity, the rate book, the card-type
#: discriminator, **the rate selector list**, specificity ranking, and the tenant
#: markup" are slice 4's, listed there expressly "so that no ticket quietly
#: widens". Slice 4 rebuilds these three schemas; converting them here would be
#: the same work twice and a second breaking change on the same six properties.
#:
#: THIS SET ONLY EVER SHRINKS, and it is not a suppression list — it is the
#: exact residue. `test_every_exemption_is_still_a_real_exposure` fails if an
#: entry stops describing a real exposure, on the same principle as the
#: migration ledger's `found:` counts being true in both directions.
SLICE_4_RATE_SELECTORS = frozenset(
    (schema, f"dim{i}")
    for schema in ("RateIn", "RateChangeIn", "RateOut")
    for i in range(1, 7)
)


def _slot_named_properties(document) -> set:
    """Every (schema name, property name) in a document naming a slot.

    The walk RECURSES, and that is not defensive programming. A schema's
    properties are not all at its top level: a nested object, an `anyOf` branch,
    an array's `items` all carry `properties` of their own, and a check that read
    only the outermost level would answer "no slot is exposed" about a document
    that exposed one inside a list. The pair is reported against the named
    component schema the property is reachable from, which is the thing a reader
    can act on.
    """
    found = set()

    def walk(name, node):
        if isinstance(node, dict):
            for prop in node.get("properties", {}):
                if SLOT_NAMED.fullmatch(prop):
                    found.add((name, prop))
            for value in node.values():
                walk(name, value)
        elif isinstance(node, list):
            for value in node:
                walk(name, value)

    for name, schema in document["components"]["schemas"].items():
        walk(name, schema)
    return found


class NoPhysicalSlotIsPublishedTest(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.document = json.loads(COMMITTED.read_text(encoding="utf-8"))

    def test_no_physical_slot_field_is_exposed_beyond_the_declared_residue(self):
        """Equality, so the residue is exact in BOTH directions.

        A superset means a slot property was published — the thing this ticket
        removed. A subset means a declared exemption no longer describes a real
        exposure, which overstates the debt; the ledger's rule for that is to
        delete the entry rather than let it stand, so slice 4 cannot half-pay
        this and leave the set claiming the whole of it.
        """
        self.assertEqual(_slot_named_properties(self.document),
                         set(SLICE_4_RATE_SELECTORS))

    def test_the_two_posting_schemas_publish_the_object_instead(self):
        """The vacuity guard, half one: the walk read its subject.

        An absence measured over a document that failed to load, or over
        schemas renamed out from under it, would pass in silence. So name the
        two schemas this ticket changed, prove they are there, and prove they
        carry the property that replaced the slots.
        """
        for schema in ("RecordUsageResponse", "UsageEventDetailOut"):
            properties = self.document["components"]["schemas"][schema]["properties"]
            self.assertIn("grouping_fields", properties, schema)
            self.assertEqual(properties["grouping_fields"]["type"], "object", schema)

    def test_the_walk_would_catch_a_slot_property_if_one_were_added(self):
        """The vacuity guard, half two: the positive control.

        The absence rests entirely on the pattern and the walk, so prove they
        FAIL on a document that does expose a slot — a pattern matching nothing
        reports the same clean result as a contract exposing nothing, and the
        two are not the same fact.
        """
        planted = {"components": {"schemas": {
            "SomeOut": {"properties": {"grouping_field_4": {"type": "string"},
                                       "provider": {"type": "string"}}},
            "SomeIn": {"properties": {"dim1": {"type": "string"}}},
        }}}
        self.assertEqual(_slot_named_properties(planted),
                         {("SomeOut", "grouping_field_4"), ("SomeIn", "dim1")})

    def test_the_walk_reaches_a_slot_nested_below_the_top_level(self):
        """The vacuity guard, half three — the recursion is load-bearing.

        `PublishIn.changes` carries `RateChangeIn` by reference, but nothing
        stops a future schema from inlining an object instead, and a slot
        property inside one would be invisible to a top-level-only walk while
        the absence above still reported clean.
        """
        planted = {"components": {"schemas": {"SomeOut": {"properties": {
            "rows": {"items": {"properties": {"dim5": {"type": "string"}}}},
        }}}}}
        self.assertEqual(_slot_named_properties(planted), {("SomeOut", "dim5")})
