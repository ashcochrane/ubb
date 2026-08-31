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

One housekeeping note, corrected in #355 because it said the opposite of what
is true and no gate reads prose. This module is **swept like any other file** —
it is in none of `gates/forbidden-term-sweep.yaml`'s seven exclusion rules, and
`checks-whose-subject-is-a-retired-word` names fourteen paths that do not
include it. Nothing about the inventory below needs an exemption today: it is a
list of real paths, and a path is tokenised on `/` and `.` like anything else,
so none of the directories it names happens to carry a retired word.

⚠ **The day one does, the answer is the exclusion and not an edit here.** The
path is data rather than prose, and re-spelling it to satisfy a sweep would
falsify the inventory to keep a gate quiet — which is the one thing this module
exists to refuse.
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
    # 3 → 4 in #355: the rule's pricing method, DERIVED from the registry
    # frozenset exactly as the posting's four are, and counted for the reason
    # the paragraph above gives — this inventory counts the shape and not the
    # provenance, so a derived list still comes past a reviewer. Re-taken from
    # the census rather than incremented: the file's other three are the kind
    # discriminator, declared once on the rule and once on its container, and
    # the rule's arithmetic shape — and a number nobody measured is a number
    # that can be wrong in either direction.
    #
    # ⚠ 4 → 3 in #367, and the one that went is the kind discriminator's use on
    # the RULE. It was declared on the rule and on its container; the rule's
    # column was deleted rather than re-spelled, so the container's was the
    # only one left.
    #
    # ⚠ 3 → 2 in #368, which is that last one going. The container split into
    # two separately shaped entities, so there is no column left for a kind
    # word to live on and no value set to declare: which kind a book is, is
    # which TABLE it sits on. Re-taken from the census rather than decremented,
    # for the reason the paragraph above gives.
    #
    # 2 -> 3 in #415: the work-level price line names the ALTITUDE of the
    # declaration it prices, and the set is `TASK_TYPE_KIND_CHOICES` IMPORTED
    # from `work/models.py` rather than a second copy written here -- the
    # `SLOT_CHOICES` import at the top of that module doing the same job for
    # the same reason. So this inventory counts a value set that is one object
    # shared with the row above it, which is the shape it should count: it
    # counts declarations of a set on a COLUMN, and a column declaring one is
    # what a reviewer needs to see whether or not the members were written
    # locally.
    "ubb-platform/apps/metering/pricing/models.py": 3,
    # 2 → 4 in #351: the price status and its reason, both DERIVED from the
    # registry frozensets exactly as the cost pair beside them. The count rises
    # because this inventory counts the shape and not the provenance — which is
    # the point of it, and the reason a derived list still has to come past a
    # reviewer.
    "ubb-platform/apps/metering/usage/models.py": 4,
    "ubb-platform/apps/platform/customers/models.py": 3,
    "ubb-platform/apps/platform/event_types/models.py": 3,
    "ubb-platform/apps/platform/events/models.py": 1,
    "ubb-platform/apps/platform/grouping_fields/models.py": 2,
    "ubb-platform/apps/platform/membership/models.py": 4,
    "ubb-platform/apps/platform/plans/models.py": 1,
    "ubb-platform/apps/platform/tenants/management/commands/seed_dev_data.py": 1,
    "ubb-platform/apps/platform/tenants/models.py": 3,
    # 2 → 3 in #409: `OUTCOME_REASON_CHOICES`, the caller's closed set of
    # reasons a unit of work did not deliver. It rises for the same reason the
    # usage models' pair above rose — this inventory counts the SHAPE and not
    # the provenance, and every value in it is held by reference from the
    # generated constants. A derived list still comes past a reviewer, which is
    # the whole point of counting shapes.
    # 3 → 4 in #414: `PRICING_MODE_CHOICES`, how a kind of work is sold. Same
    # shape and same provenance as the three above it — both identities come
    # from the generated constants and only the wording is written here — and
    # it is worth one line that this one is also the module's first column
    # declared into a transition class, so what the reviewer is being shown is a
    # value set whose members can never change ON A ROW either.
    # 4 -> 5 in #415: the SAME value set a second time, on the unit of work
    # itself. It is one concept at two scopes and the registry says the
    # repetition is deliberate — the declaration says how a KIND of work is
    # sold, the unit of work says how IT was sold, and the second is a snapshot
    # of the first taken at start so that a configuration change can never reach
    # work already running. This inventory counts shapes rather than concepts,
    # so a set reused deliberately still comes past a reviewer, which is exactly
    # what it is for.
    "ubb-platform/apps/platform/work/models.py": 5,
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
