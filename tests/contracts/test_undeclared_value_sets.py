"""The value sets the registry describes no concept for (#227).

G2 and G3 measure the consumers the registry NAMES. This module is about what
that leaves out, and it exists because leaving it out silently is the failure
`gates/README.md` spends four pages refusing.

**The gap is real and it is structural.** A `choices=` list for a concept
`domain-vocabulary/` declares nothing about cannot be a G2 finding: attributing
an enumeration to a concept means comparing its members against a registry value
set, and #191 decision 3 rules that out — *"a literal-scan is a check a
coincidence can satisfy"*. So the census cannot see it, will never be able to
see it, and the honest response is not to pretend otherwise but to **count it**.

That is what this module does. **Every Django `choices=` in living backend code
is pinned below, by file and by count** — all 50 of them across 20 files,
whether or not the registry declares a consumer for that file.

Pinning the whole inventory rather than only the unmatched part is deliberate,
and the reason is the case that would otherwise slip through: a file CAN be a
declared consumer and still carry value sets the registry says nothing about.
`apps/platform/tenants/models.py` is one — the registry gives it three concepts,
and it declares three `choices=` lists, and they are not the same three.
Partitioning by file would have called it "measured" and hidden the difference.
So the two mechanisms are kept orthogonal: G2 and G3 measure DECLARED CONCEPTS
value by value, this counts DECLARED VALUE SETS file by file, and neither
pretends to do the other's job.

The counts are literals, checked in both directions, for G7's reason: a new
value set moves a number and has to come past a reviewer, while deleting one
moves it the other way. Neither can happen in silence, which is the property
#191 story 15 asks for — *"a public value must declare its kind before it
ships"* — generalised from the one field #206 found to the class it belongs to.

**Why the backend only, stated rather than left to be noticed.** `choices=` is
Django's own declaration that a field has a closed value set: it is
self-labelling, so counting it means something. A TypeScript `as const` array is
just an array — the console's are as often React Query keys (`["billing",
"revenue-analytics"] as const`) or a component's variant list as they are domain
vocabulary, and a pinned count over them would pin noise and get raised until it
stopped failing. The SDK declares no `Literal[...]` at all, which
`test_consumer_census.py` pins separately. Both facts are checked below so that
neither can change without being seen.

One housekeeping note, because it looks like an oversight otherwise: this module
is named in the forbidden-term sweep's `checks-whose-subject-is-a-retired-word`
exclusion. It has to be — the inventory below is a list of real paths, and one
of the directories UBB has not yet renamed is spelled with a retired word. The
path is data, not prose, and editing it to satisfy a sweep would falsify the
inventory to keep a gate quiet.
"""

import pytest

from _helpers import REPO_ROOT
from tools.consumers import declared_value_sets, take_census
from tools.consumers.census import NOT_LIVING_CODE
from tools.vocabulary import load_registry

#: Every file in living backend code that declares a value set of its own, and
#: how many it declares.
#:
#: NOT a ledger. A ledger entry names the canonical term the site should carry
#: and the slice that removes it, and for most of these neither exists — there
#: is no concept to expect, and no slice owes a rename nobody has decided.
#: `gates/README.md` gives the same reason for keeping the permanent exceptions
#: in their own file: mixing in things nobody owes would make "the ledger is at
#: zero" unreachable by construction, and G22 depends on it being reachable.
#:
#: What it is instead is an inventory with a number on it. Declaring a value set
#: the agreed model says nothing about is legal — and it is legal VISIBLY.
#:
#: A COUNTED LINE IS NOT BY ITSELF A DEBT, and the posting is where that stops
#: being a theoretical distinction. Its two lists are `choices=` arguments built
#: BY COMPREHENSION over the frozensets `core.vocabulary` generates from the
#: registry, so they enumerate what a Django field is entitled to enumerate
#: while holding not one value of their own — which is why the census reads that
#: file as serving `costing_status` in full and `g2-backend-costing_status` was
#: deleted in the same commit that added these two lines. The inventory counts
#: the SHAPE, deliberately: a derived list and a typed one are indistinguishable
#: to a reader skimming a diff, so both come past one.
VALUE_SETS = {
    "ubb-platform/apps/billing/gating/models.py": 5,
    "ubb-platform/apps/billing/invoicing/models.py": 4,
    "ubb-platform/apps/billing/stripe/models.py": 1,
    "ubb-platform/apps/billing/tenant_billing/models.py": 2,
    "ubb-platform/apps/billing/topups/models.py": 2,
    "ubb-platform/apps/metering/pricing/models.py": 3,
    "ubb-platform/apps/metering/usage/models.py": 2,
    "ubb-platform/apps/platform/customers/models.py": 3,
    "ubb-platform/apps/platform/event_types/models.py": 3,
    "ubb-platform/apps/platform/events/models.py": 1,
    "ubb-platform/apps/platform/grouping_fields/models.py": 2,
    "ubb-platform/apps/platform/membership/models.py": 4,
    "ubb-platform/apps/platform/plans/models.py": 1,
    "ubb-platform/apps/platform/tenants/management/commands/seed_dev_data.py": 1,
    "ubb-platform/apps/platform/tenants/models.py": 3,
    "ubb-platform/apps/platform/work/models.py": 2,
    "ubb-platform/apps/referrals/models.py": 4,
    "ubb-platform/apps/referrals/rewards/models.py": 1,
    "ubb-platform/apps/subscriptions/models.py": 1,
    "ubb-platform/apps/billing/wallets/models.py": 5,
}


@pytest.fixture(scope="module")
def registry():
    return load_registry(REPO_ROOT / "domain-vocabulary", REPO_ROOT)


@pytest.fixture(scope="module")
def backend(registry):
    return declared_value_sets(REPO_ROOT, registry, "backend")


@pytest.fixture(scope="module")
def census(registry):
    return take_census(REPO_ROOT, registry)


# ---------------------------------------------------------------------------
# The accounting
# ---------------------------------------------------------------------------

def test_every_backend_value_set_is_accounted_for(backend):
    """THE ACCOUNTING. Every `choices=` in living backend code, pinned.

    A file or a count that is not here is a value set that arrived with nobody
    noticing, which is what this module exists to refuse. Checked in both
    directions: a new one fails, and so does a stale line for one that has
    gone, because an inventory that may overstate is an inventory with no upper
    bound.
    """
    assert {path: len(items) for path, items in backend.items()} == VALUE_SETS, (
        "the backend's declared value sets have changed. If a new one arrived, "
        "add its line — and consider whether it should have a registry concept "
        "instead (#191 story 15). If one was deleted or converted to import "
        "`core.vocabulary`, remove or lower its line in the same change.")


def test_the_inventory_and_the_census_are_orthogonal(backend, census):
    """The two mechanisms answer different questions, and both are live.

    This counts DECLARED VALUE SETS by file; G2 and G3 measure DECLARED
    CONCEPTS value by value. Some files are in both, and the fact that neither
    set contains the other is what stops either being mistaken for the other's
    coverage.

    Compared on the BACKEND only. `census.read` spans all three surfaces, so a
    comparison against the whole of it would be satisfied by the console and
    the SDK alone and would assert nothing about the surface this module is
    about.
    """
    inventory = set(backend)
    measured = {v.path for v in census.verdicts if v.surface == "backend"}
    assert measured, "the census read no backend consumer at all"

    assert inventory & measured, "no file is in both — one of the walks broke"
    assert inventory - measured, (
        "every backend file declaring a value set is also a declared consumer, "
        "so this module's stated gap has closed. Good news — but reconsider "
        "the module rather than leaving a check that can no longer find "
        "anything.")
    assert measured - inventory, (
        "every backend consumer the registry declares also keeps a `choices=` "
        "list of its own. Some — `queries.py`, `actions.py`, `reasons.py`, "
        "`services.py`, `schemas.py` — hold their values as plain module "
        "constants, and a walk that stopped seeing that difference would have "
        "stopped distinguishing the two debts G2 records.")


def test_the_walk_read_a_substantial_surface(backend):
    """A vacuity guard (#191 story 20).

    Not a pinned file count — that is the assertion above — but a floor far
    above what a broken path resolution returns. Without it, a walk that
    resolved the wrong root would report an empty inventory, and the assertion
    above would fail with a diff nobody could read as "the walk broke".
    """
    assert len(backend) >= 15, (
        f"the walk found value sets in only {len(backend)} backend files. "
        f"This tree has more than that, so the root resolved wrongly.")


def test_every_counted_file_is_in_the_tree():
    """An entry that names nothing would inflate the count and excuse nothing."""
    for path in VALUE_SETS:
        assert (REPO_ROOT / path).is_file(), f"{path} is not in the tree"


def test_no_counted_file_is_excluded_from_the_walk():
    """The two mechanisms must not overlap.

    A file both counted here and skipped as non-living code would be an entry
    that can never fail — the inert-suppression shape this repository has
    shipped three times.
    """
    for path in VALUE_SETS:
        overlapping = [part for part in NOT_LIVING_CODE if part in "/" + path]
        assert not overlapping, f"{path} is also excluded by {overlapping}"


def test_the_walk_skips_only_what_it_declares(registry):
    """Every exclusion carries a reason, and none is a bare path.

    #154 §14's warning applied here: an over-broad exclusion silently disarms
    the count, and the cheapest way for one to arrive is with no reason beside
    it.
    """
    for part, reason in NOT_LIVING_CODE.items():
        assert part.startswith("/") and part.endswith("/"), part
        assert len(reason.split()) >= 4, f"{part} carries no real reason"


# ---------------------------------------------------------------------------
# The other two surfaces: why they are not counted, checked rather than said
# ---------------------------------------------------------------------------

def test_the_sdk_declares_no_value_set_of_its_own(registry):
    """Nothing to count, so nothing is pinned — and that is a claim, not an
    omission. The SDK types these fields as bare strings, which is why #207
    generated `ubb/vocabulary.py` and why the SDK's five debts are additions
    rather than replacements."""
    found = declared_value_sets(REPO_ROOT, registry, "sdk")
    assert not found, (
        f"the SDK's hand-written surface has grown a `Literal[...]` value set: "
        f"{found}. It now needs the same accounting the backend has.")


def test_the_console_arrays_are_not_all_value_sets(registry):
    """Why the console is NOT pinned, demonstrated instead of asserted.

    A TypeScript `as const` array is just an array: React Query keys and
    component variant lists are spelled identically to a domain value set. A
    pinned count over them would pin noise and be raised until it stopped
    failing — an exclusion widened until it disarms the check, which #154 §14
    warns about by name. Django's `choices=` carries the claim in its own
    syntax, which is the whole difference.
    """
    found = declared_value_sets(REPO_ROOT, registry, "console")
    assert found, "the console declares arrays somewhere"
    query_keys = [path for path in found if path.endswith("/api/queries.ts")]
    assert query_keys, (
        "no console `as const` array is a query key any more. If that is real, "
        "the console may now be countable the way the backend is — reconsider "
        "this module's stated limit rather than deleting this test.")
