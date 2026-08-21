"""The five markup routes are off the router, and no route writes their acts (#369).

The tenant-level markup record is deleted with its five routes — a tenant-scope
read and write, and a customer-scope read, write and delete — its two component
schemas, and both of the audit action names those routes carried. **Deleting an
action whose act no longer exists is not the rename ADR-004 §2 governs.** A
rename carries an act forward under a new spelling and breaks a reader watching
for the old one; these two have no successor to carry forward, because the acts
themselves stopped happening: the record they were performed on is gone, and
what replaced each half is a different act on a different record — a tenant
DECLARES a default markup rung (#357), and a customer's own price is a rule
declared through a publish on their own Pricing Book (#361).

**NO PART OF THE ONE-TIME PRE-PRODUCTION AUDIT-REGISTRY RESET IS CONSUMED.**
#154 §4.2 defines that exception and #154 §13 / #155 §14 allocate it to slice 8,
for the actions that genuinely ARE renamed. This commit draws against none of it.

⚠ **THE REFUSAL HALF IS NOT HERE, AND WHERE IT IS IS A SWEEP DECISION RATHER
THAN A TASTE ONE.** Asserting that `record()` refuses each name means reaching
those names, and every one of their five ledger entries reaches ZERO in this
commit — so a module carrying either word would put its count back over an entry
that no longer exists. That half is in
`apps/metering/pricing/tests/test_the_markup_record_is_deleted.py`, which
DERIVES the noun from the deleting migration's own from-state and composes the
two names from ordinary verbs.

What is here is the half whose subject is the ROUTER: that none of the five
paths is served, and that the pair which REPLACED them is declared on the routes
that write it. It spells nothing retired because it walks the live API and asks
what is there. A module under `apps/**/tests/` importing `api.v1.tests.*` is
invisible to the boundary gate and still wrong (#367), so a router-walk test
belongs here.

⚠ **"NO SURVIVING ROUTE WRITES AN UNREGISTERED ACTION" IS NOT ASSERTED HERE,
BECAUSE IT ALREADY IS.** `test_audit_sweep.py::test_declared_actions_are_
registered` walks the same `mutating_operations()` and requires every declared
action to be in the registry — so a case here would restate it over the same
walk with no added discrimination, and two copies of one search agreeing prove
nothing. With the two names out of the registry, that existing test is what
turns a route still declaring one red.
"""
from django.test import SimpleTestCase

from api.v1.api import api
from api.v1.tests.test_audit_sweep import mutating_operations

#: The five paths, exactly as the router spelled them. Two distinct paths, five
#: operations: the tenant scope carried a GET and a PUT, the customer scope a
#: GET, a PUT and a DELETE.
THE_PATHS_THAT_CEASED = (
    "/metering/pricing/markup",
    "/metering/pricing/customers/{customer_id}/markup",
)

#: What a tenant reaches instead, and what makes the two paths above removals
#: rather than renames: a different record, declared rather than set, carrying
#: ONE term because a margin over cost never composes with a flat addend.
THE_PATH_THAT_REPLACES_THE_TENANT_HALF = "/metering/pricing/default-markup"


def _live_paths():
    """Every path the live API serves, mount-prefixed and without the root.

    The same shape `mutating_operations()` yields and `THE_PATHS_THAT_CEASED`
    is written in — built the same way rather than by string concatenation,
    because a prefix and a path each carry their own leading slash and joining
    them naively produces a path this API has never served, which would make
    every absence below true for the wrong reason.
    """
    paths = set()
    for prefix, router in api._routers:
        for path in router.path_operations:
            segments = [s for s in (prefix.strip("/"), path.strip("/")) if s]
            paths.add("/" + "/".join(segments))
    return paths


class NoneOfTheFiveOperationsIsServedTest(SimpleTestCase):
    """The routes, asked of the router rather than of a source file.

    A grep over `metering_endpoints.py` would pass against a route that had
    merely moved modules. This walks what the API actually mounts.
    """

    def test_neither_path_is_on_the_api_at_all(self):
        served = _live_paths()

        for path in THE_PATHS_THAT_CEASED:
            with self.subTest(path):
                self.assertNotIn(path, served)

    def test_the_rung_that_replaced_the_tenant_half_IS_served(self):
        """The vacuity guard, and the claim worth making beside the absence.

        Every assertion above would pass against an API that had lost its
        whole pricing surface, or against a path spelled wrongly here. This is
        the case that says the replacement is reachable — which is what makes
        the five deletions a move rather than a loss.
        """
        self.assertIn(THE_PATH_THAT_REPLACES_THE_TENANT_HALF, _live_paths())


class TheRungThatReplacedThemDeclaresItsOwnPairTest(SimpleTestCase):
    """The positive half, so the absences above cannot read as a silent loss.

    ⚠ **ASKED OF THE ROUTES RATHER THAN OF THE REGISTRY.** That the two deleted
    names are unregistered is the OTHER module's claim, derived rather than
    spelled; that no route declares an unregistered name is already
    `test_audit_sweep.py`'s, over this same walk. What is left for this module
    is the one thing neither says: which routes carry the pair that replaced
    them, as an exact map rather than a membership check.
    """

    def test_the_surviving_rung_declares_the_pair_that_replaced_them(self):
        """And the pair that DID survive is on the routes it belongs to, so
        "no route writes the retired acts" cannot be read as "markup governance
        stopped being recorded at all"."""
        declared = {
            (method, path): getattr(view_func, "_audit_actions", ())
            for method, path, view_func in mutating_operations()
            if path == THE_PATH_THAT_REPLACES_THE_TENANT_HALF
        }

        self.assertEqual(
            declared,
            {("PUT", THE_PATH_THAT_REPLACES_THE_TENANT_HALF):
                ("tenant_default_markup.declared",),
             ("DELETE", THE_PATH_THAT_REPLACES_THE_TENANT_HALF):
                ("tenant_default_markup.withdrawn",)})
