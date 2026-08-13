"""The whole route family is published under the canonical noun (#278, AC 1).

Three paths and four operations: the registry collection route in both
directions, the registry's value-listing route, and the margin breakdown route —
which is the least obvious member of the family, sits in a different product's
API module, and is here because the ledger splits the debt on the singular form
and the singular is this slice's.

**What this file does NOT prove, and where that proof lives instead.**

*That the retired word is gone from the published contract* is the
forbidden-term sweep's claim, not a pin's. The contract surface's ledger entry
for that word reaching a recorded extent of zero, and being deleted for it, IS
that proof; it is checked by `python -m tools.forbidden_terms` and by
`tests/contracts`, and a second copy here could only ever raise the question of
which copy was right. The same argument keeps this file from spelling a retired
term anywhere the sweep would match one — including inside a ledger entry's id,
where the hyphens leave the word a whole token. A retired word inside a longer
identifier is invisible to that matcher and so appears here where naming a file
requires it, which is the matcher's rule and not a loophole. The sweep counts
FILES per term, so a new file spelling one would push another slice's recorded
extent wider, and a debt is a finite migration plan rather than a licence for
the word to reach further while it stands.

*That the old paths were removed rather than merely joined by new ones* is the
cumulative breaking gate's claim. Removing a published path and a published
operation identifier are both breaks, both appear in the accepted-break block
this change generates, and `python openapi/contract_gate.py` refuses an
unreviewed one.

*That the routes still work* is proved where it always was — beside the request
shapes, in `api/v1/tests/test_grouping_field_registry.py` for the registry pair and
its values, and in `apps/subscriptions/tests/test_margin_endpoints.py` for the
breakdown. The registry round trip has to stay in that first file: driving it
means spelling the declaration request's own property, a plural this slice does
not own, and a new file spelling it would push that recorded extent wider. The
breakdown round trip stays in the second for the ordinary reason — it is where
that endpoint's tests live — and not for the vocabulary reason: after this
commit that file carries no retired word at all.

What is left is the claim nothing else makes: the family's published IDENTITY —
method, path and operation identifier — is exactly these four, and no fifth
operation anywhere in the contract answers to the canonical noun.
"""
import json

from django.test import TestCase

from api.v1.openapi_export import COMMITTED_SPEC_PATH as COMMITTED

#: The canonical noun, in the two spellings a published document uses it in: a
#: path segment is kebab-cased and an operation identifier is a Python
#: identifier. Both are searched, because a rename that reached one and not the
#: other is exactly the half-done state this ticket exists to remove.
CANONICAL = ("grouping-field", "grouping_field")

#: Every operation the family publishes, as the contract identifies one:
#: **method AND path** (ADR-0007 §4), plus the operation identifier that names
#: its generated module.
#:
#: The margin breakdown route is listed last because it is the member a reader
#: is most likely to think does not belong. It does: slice 7 later absorbs it
#: into a five-endpoint collapse, so this slice renames a route that slice will
#: then take — churn that was weighed and decided by the ledger's ownership
#: rule, which lets a debt move earlier and never later.
FAMILY = frozenset({
    ("put", "/api/v1/metering/grouping-fields",
     "api_v1_metering_endpoints_declare_grouping_fields"),
    ("get", "/api/v1/metering/grouping-fields",
     "api_v1_metering_endpoints_list_grouping_fields"),
    ("get", "/api/v1/metering/grouping-fields/{key}/values",
     "api_v1_metering_endpoints_list_grouping_field_values"),
    ("get", "/api/v1/margin/by-grouping-field",
     "apps_subscriptions_api_margin_endpoints_margin_by_grouping_field"),
})


def _operations_answering_to_the_canonical_noun(document) -> set:
    """Every published operation whose path or identifier names the noun.

    Collected by SEARCHING the whole document rather than by looking the four
    up, so the assertion below can be an equality. Looking them up would prove
    the four arrived and say nothing about a fifth — and a fifth is the likely
    shape of a mistake here, because the family is spread across two API
    modules and a route added to one of them under this noun would otherwise
    join the surface unremarked.
    """
    return {
        (method, path, operation.get("operationId", ""))
        for path, operations in document["paths"].items()
        for method, operation in operations.items()
        if isinstance(operation, dict)
        and any(word in path or word in operation.get("operationId", "")
                for word in CANONICAL)
    }


class TheRouteFamilyIsPublishedUnderTheCanonicalNounTest(TestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.document = json.loads(COMMITTED.read_text(encoding="utf-8"))

    def test_the_family_is_exactly_these_four_operations(self):
        """Equality, so the set is exact in both directions.

        A missing member is a route the rename did not reach. An extra member
        is a route that joined the family without anyone deciding it had.
        """
        self.assertEqual(
            _operations_answering_to_the_canonical_noun(self.document),
            set(FAMILY))

    def test_the_breakdown_row_names_the_value_rather_than_the_axis(self):
        """The vacuity guard, half one: the document read is the real one.

        An equality over a set collected from a document that failed to load,
        or whose schemas were renamed out from under the collector, would pass
        in silence. So name the schema this ticket reshaped and prove it
        carries the property that replaced the retired one.

        The property is the ledger's own `expected` for this site. Why a row
        names the value and not the axis is argued once, on the schema itself
        in `apps/subscriptions/api/margin_schemas.py`, rather than repeated
        wherever the name shows up.
        """
        row = self.document["components"]["schemas"]["GroupingFieldMarginRow"]
        self.assertIn("grouping_field_value", row["properties"])

    def test_the_collector_would_catch_a_fifth_operation(self):
        """The vacuity guard, half two: the positive control.

        The equality rests entirely on the collector, and a collector that
        matched nothing would report the same clean result as a contract
        publishing exactly the right four. They are not the same fact.
        """
        planted = {"paths": {
            "/api/v1/somewhere/grouping-fields/{key}/rollup": {
                "get": {"operationId": "somewhere_rollup"}},
            "/api/v1/elsewhere": {
                "post": {"operationId": "elsewhere_declare_grouping_field"}},
            "/api/v1/unrelated": {"get": {"operationId": "unrelated"}},
        }}
        self.assertEqual(
            _operations_answering_to_the_canonical_noun(planted),
            {("get", "/api/v1/somewhere/grouping-fields/{key}/rollup",
              "somewhere_rollup"),
             ("post", "/api/v1/elsewhere",
              "elsewhere_declare_grouping_field")})

    def test_the_collector_reads_both_spellings_independently(self):
        """The vacuity guard, half three — searching both is load-bearing.

        Django Ninja derives an operation identifier from the view function's
        module and name, and the path is written by hand in the decorator
        beside it. Nothing makes them agree. A rename that moved one and left
        the other would publish a route whose identity contradicts itself, and
        a collector reading only one spelling would report it clean.
        """
        path_only = {"paths": {"/api/v1/metering/grouping-fields": {
            "get": {"operationId": "api_v1_metering_endpoints_list_axes"}}}}
        identifier_only = {"paths": {"/api/v1/metering/axes": {
            "get": {"operationId":
                    "api_v1_metering_endpoints_list_grouping_fields"}}}}
        for document in (path_only, identifier_only):
            self.assertEqual(
                len(_operations_answering_to_the_canonical_noun(document)), 1)
