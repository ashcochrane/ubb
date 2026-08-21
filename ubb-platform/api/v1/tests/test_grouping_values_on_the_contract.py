"""Which published schemas name a physical slot, and which may (#277, #366).

Two claims held as ONE EQUALITY, because they are the same fact read in two
directions: no schema exposes a physical slot except the rate's three, and those
three expose all ten of them under the column names.

⚠ **IT STARTED AS A PURE ABSENCE AND IS NOT ONE ANY MORE (#366).** Ticket 20's
version asserted that nothing published a slot beyond a declared residue of
eighteen `dim<n>` pairs it could not remove. Ruling 15 decided that residue the
other way: a rate's selectors ARE its columns, so the rate schemas keep them,
take the column names, and gain the four slots that had no published property at
all. What remains an absence is everything else — a posting's grouping values,
an analytics row, a change body — and that half still carries both halves of a
vacuity guard: a positive control proving the walk FAILS on a document that does
expose a slot, and a pin on the two schemas ticket 20 changed proving the walk
read its actual subject.

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

from api.v1 import schemas
from api.v1.openapi_export import COMMITTED_SPEC_PATH as COMMITTED
from apps.platform.grouping_fields.models import SLOTS

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

#: WHERE A PHYSICAL SLOT IS PUBLISHED ON PURPOSE — the rate's selector list, and
#: nothing else.
#:
#: ⚠ **THIS SET CHANGED CHARACTER WITH #366 AND IT IS NOT A DEBT ANY MORE.** It
#: was eighteen pairs of `dim<n>` on three schemas: six published names sitting
#: over six differently-named columns, held here as a residue that only ever
#: shrank because #276 had renamed the columns and deliberately renamed no
#: published property. Ticket 20 (#277) read its own acceptance criteria wider
#: ("no physical slot field is exposed on any public schema") and left the
#: question open; **#193 §L decided it** — "the rate entity, the rate book, the
#: card-type discriminator, **the rate selector list**, specificity ranking, and
#: the tenant markup" are slice 4's, listed there expressly "so that no ticket
#: quietly widens".
#:
#: Slice 4 took it, and the answer was NOT to remove the properties. **A rate's
#: selectors are ITS COLUMNS, and there are ten of them.** The three schemas now
#: publish `grouping_field_1`..`grouping_field_10` under the column names, so the
#: count goes UP — eighteen to thirty — while the thing this file was written to
#: refuse goes away entirely: there is no longer a second spelling for a slot,
#: and the join dictionary that translated one into the other is deleted.
#:
#: **WHY THAT IS NOT THE DEFECT THE POSTING SIDE HAS.** A posting's grouping
#: values are the TENANT'S facts, keyed by the tenant's own declared key, so a
#: physical slot on that surface leaks UBB's internal identity for a binding the
#: tenant knows by another name — and re-binding a key would silently change
#: what a published field meant. A rate's selector list is the RULE'S own shape:
#: a rule is pinned on the columns it is pinned on, `Rate.SELECTORS` is exactly
#: those columns, and a body naming them says precisely which rule it addresses.
#: The tenant-key spelling exists too, on the publish act (#358's
#: `grouping_fields` object), and it is the one to reach for. These three are the
#: immediate routes, and they speak the table's vocabulary.
#:
#: THE SET IS AN EQUALITY IN BOTH DIRECTIONS. Larger means a slot property was
#: published somewhere nobody decided it should be; smaller means this file
#: claims an exposure the contract does not have, which is the migration
#: ledger's `found:` rule applied to a set.
#: The published schemas that name a rule's selector columns — spelled once so
#: the equality below and the rename check further down cannot drift apart.
#:
#: ⚠ **ONE, NOT THREE, SINCE #368.** Both bodies that named a slot by its
#: COLUMN have left with their routes: the immediate add-a-rule body with #367,
#: the immediate reprice body with #368. Adding, repricing and retiring a rule
#: are declared changes on a publish now, and that body names a slot by the
#: tenant's own declared KEY. What is left here is the row a read answers with.
#:
#: ⚠ **RULING 15's GAP STAYS CLOSED, THROUGH THE OTHER VOCABULARY.** The gap
#: was that a rule pinned on the seventh slot could be written server-side and
#: repriced by no body in existence. `BookChangeIn.grouping_fields` reaches
#: every slot a tenant has declared, whichever slot the registry bound it to,
#: so the rule is reachable — by key rather than by column. The set below falls
#: by ten because a SURFACE left, not because a slot did, and
#: `test_a_rate_on_any_slot_can_be_repriced.py` is where that is driven end to
#: end.
RATE_SCHEMAS = ("RateOut",)

RATE_SELECTOR_PROPERTIES = frozenset(
    (schema, slot)
    for schema in RATE_SCHEMAS
    for slot in SLOTS
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

    def test_no_physical_slot_field_is_exposed_beyond_the_rate_selector_list(self):
        """Equality, so the set is exact in BOTH directions.

        A superset means a slot property reached a schema nobody decided should
        carry one — the thing this file was written to catch. A subset means the
        set claims an exposure the contract does not have, which is the same
        defect as a ledger entry recording more files than the tree holds.

        ⚠ **THIRTY, NOT EIGHTEEN, AND THE RISE WAS THE POINT (#366).** Reading
        a growth here as a regression would be reading the count instead of the
        claim: twelve of those pairs were the four slots that had NO published
        property at all, and their absence is what made a rule pinned on the
        seventh slot unreachable through the API.

        ⚠ **AND THEN TWENTY, WHICH IS A SURFACE LEAVING RATHER THAN A SLOT
        (#367).** The immediate add-a-rule body is deleted with its route, so
        its ten pairs go with it — every slot is still published on the
        surviving schemas, which is what the derivation from `SLOTS` says and
        why the fall cannot hide one.

        ⚠ **AND THEN TEN, THE SAME WAY (#368).** The immediate reprice body
        went with ITS route, and it was the second of the two schemas that
        named a slot by its column. What is left is the row a read answers
        with. A change to a book names a slot by the tenant's own declared KEY,
        so `BookChangeIn` carries no slot property to count — which is why
        ruling 15's gap stays closed while this number falls twice.
        """
        self.assertEqual(_slot_named_properties(self.document),
                         set(RATE_SELECTOR_PROPERTIES))

    def test_the_rate_schemas_name_the_columns_and_no_second_spelling(self):
        """The rename half, which the equality above cannot separate out.

        `SLOT_NAMED` matches BOTH spellings a slot has ever had, so the set
        above would be satisfied by thirty `dim<n>` properties just as happily
        as by thirty column names — and the whole of ruling 15's second half is
        that the published property IS the column. Asserted positively on the
        three schemas, and negatively over the whole document so no other schema
        can quietly reintroduce the retired spelling.
        """
        published = _slot_named_properties(self.document)
        for schema, prop in published:
            with self.subTest(schema=schema, property=prop):
                self.assertIn(prop, SLOTS)
        for schema in RATE_SCHEMAS:
            properties = self.document["components"]["schemas"][schema]["properties"]
            self.assertEqual({p for p in properties if SLOT_NAMED.fullmatch(p)},
                             set(SLOTS), schema)

    def test_nothing_maps_a_published_name_to_a_column(self):
        """The join dictionary is DELETED rather than widened (#366).

        Widening it to ten would have coined four more published properties
        under the spelling this slice retires, and left a translation step
        between a reprice body and `Rate.SELECTORS` that could rename a slot
        into the wrong one. The properties take the column names, so there is
        nothing to join — and an absence needs asserting, because the module
        would import perfectly well with the dict quietly restored.

        Read off the MODULE rather than by trying an import: `assertRaises(
        ImportError)` around one name proves nothing about a differently-named
        map doing the same job. This asks the stronger question — does anything
        at `api.v1.schemas`'s top level map a published property name onto a
        column name — and it catches such a map under ANY name.

        ⚠ **THE SCOPE IS THE MODULE, NOT THE TREE, AND SAYING SO IS THE POINT.**
        A dict built inside a function body, or one that reappeared in
        `metering_endpoints.py`, is outside this walk. That is not a hole left
        open: the dict was a module constant here and this is where a
        reintroduction would go, while a translation reintroduced anywhere at
        all is caught behaviourally instead — the equality above pins what the
        three schemas publish, and
        `api/v1/tests/test_a_rate_on_any_slot_can_be_repriced.py` fails if a
        body key reaches the wrong column, which is the only damage such a map
        can actually do.
        """
        maps = {
            name: value for name, value in vars(schemas).items()
            if isinstance(value, dict)
            and any(isinstance(k, str) and isinstance(v, str)
                    and k != v and SLOT_NAMED.fullmatch(v)
                    for k, v in value.items())
        }
        self.assertEqual(maps, {})

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

        A schema can carry another by reference, and nothing stops a future
        one from inlining an object instead — a slot property inside one would
        be invisible to a top-level-only walk while the absence above still
        reported clean.
        """
        planted = {"components": {"schemas": {"SomeOut": {"properties": {
            "rows": {"items": {"properties": {"dim5": {"type": "string"}}}},
        }}}}}
        self.assertEqual(_slot_named_properties(planted), {("SomeOut", "dim5")})
