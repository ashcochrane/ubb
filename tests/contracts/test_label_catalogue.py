"""G6 — the registry owns identity, the console owns expression (#210, ADR-0008 §4).

Two questions, one gate, and they are enforced here together because the answer
to the second is what makes the first survivable.

**Coverage, both ways.** ADR-0008 §4.2 asks for four things: every required
registry value has a label; every console label refers to a valid registry
value; no retired token remains labelled; every supported locale carries the
key. A one-way check would let the catalogue accumulate wording for values
nobody serves, which is how a retired token keeps its life after the code that
produced it is gone.

**And nothing renders a name any other way.** Coverage alone proves the
catalogue is complete, not that it is *used*. `apps/ui/src/lib/labels.ts` still
hand-writes twenty-nine value maps and nine files still import its humaniser,
and ADR-0008 §4.3 reverses #154 §9.1 to call that a defect rather than a soft
landing: title-casing a retired token manufactures user-facing terminology out
of an implementation token. #210 does not delete it — forty-seven files import
that module — so it survives as an explicit legacy adapter, and every one of its
debts is a migration-ledger entry with an owner slice.

**A collected debt stays collected.** Section 4 is a fourth question the three
above cannot ask: the ledger and the console agree with each other even when
both revert, so a debt already paid is pinned by id and held to both sides.

**The ledger IS the allowlist.** There is no second list of permitted sites: a
new map or a new humanising import is a ledger addition, and `tools.gates
ratchet` already refuses one without a reviewed seeding authorisation. That is
the whole mechanism, and it is why this file compares the tree against
`gates/migration-ledger.yaml` rather than against a constant of its own. A
constant would be the second encoding ADR-0006 §4 warns about, and #203's
agreement test exists because that copy was made once already.

**What this gate does NOT prove.** That the wording is any good, that it is
consistent with a style guide, or that a translation is accurate. Those are
judgement, and ADR-0008 §1 keeps them human. It proves that a value has words,
that the words name something real, and that nothing invents them.
"""

import json
import re

import pytest

from _helpers import ABSENT, REPO_ROOT, concept, load
from tools.gates import load_programme
from tools.labels import (
    Catalogue,
    Locale,
    coverage_faults,
    read_catalogue,
    required_keys,
    retired_labels,
    scan_legacy,
    split_key,
)
from tools.labels import errors as codes
from tools.labels.catalogue import DEFAULT_LOCALE, LOCALES_DIR
from tools.labels.legacy import (
    ADAPTER,
    ADAPTER_SPECIFIER,
    CONSOLE_ROOT,
    DECLARED_NON_LABEL_EXPORTS,
    HUMANISER,
    MAP_CONSTRUCTOR,
)
from tools.vocabulary import load_registry

GATE = "G6"
GATES_DIR = REPO_ROOT / "gates"

#: Every console file that imports the legacy adapter today — the set
#: `test_the_adapter_gains_no_new_importer` holds to a ratchet. Pinned as a
#: literal rather than counted, for the reason #206 pins its exclusion set: a
#: count alone would let one file be converted while another was added, and the
#: net zero would read as "nothing happened".
ADAPTER_IMPORTERS = (
    "apps/ui/src/components/shared/nav-shell.tsx",
    "apps/ui/src/features/billing/components/usage-invoices-card.tsx",
    "apps/ui/src/features/customers/components/adjust-dialogs.tsx",
    "apps/ui/src/features/customers/components/budget-section.tsx",
    "apps/ui/src/features/customers/components/business-rollup.tsx",
    "apps/ui/src/features/customers/components/grants-section.tsx",
    "apps/ui/src/features/customers/components/overview-tab.tsx",
    "apps/ui/src/features/customers/components/past-limit-section.tsx",
    "apps/ui/src/features/customers/components/revenue-panels.tsx",
    "apps/ui/src/features/customers/components/subscription-tab.tsx",
    "apps/ui/src/features/customers/components/transactions-section.tsx",
    "apps/ui/src/features/customers/components/usage-invoices-section.tsx",
    "apps/ui/src/features/dashboard/components/dimension-breakdown.tsx",
    "apps/ui/src/features/developers/components/test-event-response.tsx",
    "apps/ui/src/features/events/components/event-filters.tsx",
    "apps/ui/src/features/events/components/events-page.tsx",
    "apps/ui/src/features/events/components/ledger-table.tsx",
    "apps/ui/src/features/events/components/past-limit-panel.tsx",
    "apps/ui/src/features/events/components/stop-context-timeline.tsx",
    "apps/ui/src/features/events/components/task-section.tsx",
    "apps/ui/src/features/events/components/timeseries-card.tsx",
    "apps/ui/src/features/events/lib/search.ts",
    "apps/ui/src/features/pricing/components/add-rate-dialog.tsx",
    "apps/ui/src/features/pricing/components/book-detail-page.tsx",
    "apps/ui/src/features/pricing/components/books-table.tsx",
    "apps/ui/src/features/pricing/components/publish-row.tsx",
    "apps/ui/src/features/pricing/components/rates-table.tsx",
    "apps/ui/src/features/referrals/components/attribute-referral-dialog.tsx",
    "apps/ui/src/features/referrals/components/ledger-dialog.tsx",
    "apps/ui/src/features/referrals/components/program-form.tsx",
    "apps/ui/src/features/referrals/components/program-section.tsx",
    "apps/ui/src/features/referrals/components/referrals-table.tsx",
    "apps/ui/src/features/referrals/lib/program-form.ts",
    "apps/ui/src/features/settings/api/mock.ts",
    "apps/ui/src/features/settings/components/audit-log-page.tsx",
    "apps/ui/src/features/settings/components/billing-mode-card.tsx",
    "apps/ui/src/features/settings/components/invitations-section.tsx",
    "apps/ui/src/features/settings/components/members-section.tsx",
    "apps/ui/src/features/settings/components/products-card.tsx",
    "apps/ui/src/features/settings/components/tenant-billing-page.tsx",
    "apps/ui/src/features/settings/lib/settings.ts",
    "apps/ui/src/features/webhooks/api/mock.ts",
    "apps/ui/src/features/webhooks/components/deliveries-table.tsx",
    "apps/ui/src/features/webhooks/components/webhook-config-table.tsx",
    "apps/ui/src/features/webhooks/lib/event-groups.ts",
    "apps/ui/src/features/webhooks/lib/schemas.test.ts",
    "apps/ui/src/hooks/use-current-role.ts",
)

#: The module specifier of any `import ... from "x"` — what a file actually
#: resolves, as opposed to what a line happens to contain. BOTH quote styles:
#: the console's eslint configuration declares no `quotes` rule, so a
#: single-quoted specifier is lint-clean and a `"`-only pattern would simply not
#: see it.
IMPORT_SPECIFIER = re.compile(r"""from\s+["']([^"']+)["']""")


@pytest.fixture(scope="module")
def registry():
    return load_registry(REPO_ROOT / "domain-vocabulary", REPO_ROOT)


@pytest.fixture(scope="module")
def shipped():
    catalogue, faults = read_catalogue(REPO_ROOT)
    return catalogue, faults


@pytest.fixture(scope="module")
def legacy():
    return scan_legacy(REPO_ROOT)


@pytest.fixture(scope="module")
def programme():
    return load_programme(GATES_DIR, REPO_ROOT)


# ---------------------------------------------------------------------------
# 1. The catalogue is readable at all
# ---------------------------------------------------------------------------

def test_the_shipped_catalogue_loads(shipped):
    """Vacuity guard, and the first half of "every supported locale".

    Every comparison below is a set operation against this catalogue. A missing
    directory, an unparseable file or a locale nobody imports would leave them
    all comparing against nothing and passing — which is precisely the failure
    mode this repository has shipped three times.
    """
    catalogue, faults = shipped
    assert not faults, "\n".join(str(fault) for fault in faults)
    assert catalogue.locales, f"no locale loaded from {LOCALES_DIR}"
    assert catalogue.locale(DEFAULT_LOCALE) is not None
    assert len(catalogue.keys) > 100, (
        "the catalogue is implausibly small for a registry with this many "
        "valued concepts — check the walk, not the wording")


# ---------------------------------------------------------------------------
# 2. Coverage, in both directions
# ---------------------------------------------------------------------------

def test_every_registry_value_has_wording_in_every_locale(shipped, registry):
    """ADR-0008 §4.2's first promise AND its fourth, and §4.3's reversal made real.

    A missing label fails HERE — at the gate — rather than being humanised into
    invented copy at render time. The required set is asked of the generator's
    own `label_key`, so the key spelled here is by construction the key the
    console imports.

    The fourth promise — *every supported locale carries the required key* — is
    not a separate node, because it is not a separate question: `coverage_faults`
    asks the first promise once per loaded locale. Today there is one, so the
    loop runs once and the promise is trivially met; the day a second catalogue
    lands, a half-translated one fails here with no edit. A node comparing the
    locales against EACH OTHER was written and then deleted: with one locale it
    compared a set with itself, and with two it could only report what this
    already reports. A check that cannot fail is worse than no check, because
    the manifest would go on naming it as evidence.
    """
    catalogue, _ = shipped
    required = required_keys(registry)
    assert required, "the registry declares no label keys at all"

    findings = [f for f in coverage_faults(required, catalogue, registry)
                if f.code in (codes.UNLABELLED_VALUE, codes.BLANK_LABEL)]
    assert not findings, "\n".join(str(finding) for finding in findings)


def test_every_label_names_a_live_registry_value(shipped, registry):
    """ADR-0008 §4.2's second promise — the direction a coverage check forgets.

    Without it the catalogue only grows: wording for a value that was renamed
    two slices ago sits beside wording for the value that replaced it, and
    nothing distinguishes them.
    """
    catalogue, _ = shipped
    findings = [f for f in coverage_faults(required_keys(registry), catalogue,
                                           registry)
                if f.code in (codes.UNKNOWN_KEY, codes.RETIRED_KEY)]
    assert not findings, "\n".join(str(finding) for finding in findings)


def test_no_retired_token_keeps_its_wording(shipped, registry):
    """ADR-0008 §4.2's third promise, on its own evidence.

    Implied by the two above *today* — a retired token is not a registry value,
    so it is already an unknown key — but that is a property of this registry
    rather than of the rule. Stated separately so narrowing the equality later
    cannot silently drop it, and asked of the catalogue's own keys rather than
    of a set difference.
    """
    catalogue, _ = shipped
    still_labelled = retired_labels(catalogue, registry)
    assert not still_labelled, "\n".join(
        f"`{key}` words `{token}`, retired by `{by}`"
        for key, token, by in still_labelled)


def test_every_key_is_a_prefix_and_a_value(shipped):
    """A key the catalogue cannot be taken apart into is one the retired-token
    check cannot inspect. Without this, a key of the wrong shape would pass
    every assertion above by being invisible to the one that matters."""
    catalogue, _ = shipped
    malformed = sorted(key for key in catalogue.keys if split_key(key) is None)
    assert not malformed, f"not `<prefix>.<value>`: {malformed}"


# ---------------------------------------------------------------------------
# 3. Nothing renders a name any other way
# ---------------------------------------------------------------------------

def test_the_legacy_adapter_is_where_the_gate_thinks_it_is(legacy):
    """Vacuity guard for section 3. A moved or renamed adapter would turn every
    comparison below into a comparison of two empty sets, and the ledger's
    thirty-nine entries into unreachable ones."""
    scanned, faults = legacy
    assert not faults, "\n".join(str(fault) for fault in faults)
    assert (REPO_ROOT / ADAPTER).is_file()
    assert scanned.maps, "no hand-written value map found — the scanner is blind"


def test_the_ledger_records_exactly_what_the_legacy_adapter_still_does(legacy,
                                                                       programme):
    """The allowlist, held in both directions.

    An unrecorded site is the failure that matters most: a map or a humanising
    import nobody owes, invisible to the ratchet, cleared by nobody — #155
    §17's failure hiding inside the mechanism built to close it. The other
    direction matters too, and differently: an entry for a site that no longer
    exists is a debt already paid, and leaving it in place makes "the ledger is
    at zero" arrive later than the work did.
    """
    scanned, _ = legacy
    faults = disagreements(set(scanned.sites), recorded(programme, GATE),
                           excepted(programme, GATE))
    assert not faults, (
        "the console and gates/migration-ledger.yaml disagree.\n  "
        + "\n  ".join(faults))


def test_a_permanent_exception_is_a_site_the_scanner_sees(legacy, programme):
    """The Stripe-vocabulary maps are excused, not invisible.

    An exception naming a site the scanner does not report would suppress
    nothing while looking like it does — the same unfalsifiable shape the G9
    exception is held to in the platform suite.
    """
    scanned, _ = legacy
    excepted = {record.site for record in programme.exceptions
                if record.gate == GATE}
    assert excepted, "no permanent exception recorded for this gate"
    assert excepted <= set(scanned.sites), (
        f"excused but not found in the tree: {sorted(excepted - set(scanned.sites))}")


def test_a_debt_and_an_exception_are_never_the_same_site(programme):
    """A site owed by a slice and simultaneously declared as never being fixed
    would keep the ledger off zero forever."""
    both = recorded(programme, GATE) & {record.site
                                        for record in programme.exceptions
                                        if record.gate == GATE}
    assert not both, f"recorded as both a debt and an exception: {sorted(both)}"


def test_nothing_escapes_the_one_adapter(legacy):
    """Three ways the allowlist could be true and meaningless, stated directly.

    A second `humanize` declared anywhere in the console; a value map built
    without the `export const` the scanner reads; an `export { … }` clause that
    exports a name no declaration shows. Each would let a caller reach the
    retired behaviour while the ledger went on naming the files that do.

    `scan_legacy` already reports all three as faults, and section 3's first
    test asserts there are none. This states the rule again because that
    assertion reads as an infrastructure check — "the scan worked" — rather than
    as this gate firing, and the two failures want different reactions.
    """
    _, faults = legacy
    escaped = [fault for fault in faults if fault.code == codes.ADAPTER_ESCAPED]
    assert not escaped, "\n".join(str(fault) for fault in escaped)


def test_the_adapter_is_imported_one_way(legacy):
    """The scanner reads import statements, so it can only see the spelling it knows.

    A relative import of the same module — `./labels`, `../lib/labels` — resolves
    to exactly the same file and would slip past the allowlist entirely. So this
    reads every import SPECIFIER in the console and fails on any whose last
    segment is `labels` and which is not the canonical one. Checking the
    specifier rather than the line is what makes it exhaustive: `"labels" in
    line` would miss `from "../lib/labels"` in a file under `src/lib/`, which is
    the one place the shortcut is most tempting.
    """
    scanned, _ = legacy
    offenders = []
    for path in sorted((REPO_ROOT / CONSOLE_ROOT).rglob("*.ts*")):
        for specifier in IMPORT_SPECIFIER.findall(path.read_text(encoding="utf-8")):
            if specifier == ADAPTER_SPECIFIER:
                continue
            if specifier.rsplit("/", 1)[-1].removesuffix(".ts") == "labels":
                offenders.append(
                    f"{path.relative_to(REPO_ROOT).as_posix()}: "
                    f"imports `{specifier}`")
    assert not offenders, (
        f"the adapter must be imported as `{ADAPTER_SPECIFIER}`, so that the "
        f"allowlist can see every site that reaches it:\n  "
        + "\n  ".join(offenders))
    assert scanned.humanisers, "no humanising site found — the import scan is blind"


def test_every_adapter_export_is_classified(legacy):
    """An export nobody classified is one nobody is watching.

    The gate refuses to guess: a new export of the legacy adapter is either a
    ledgered debt or an entry in `DECLARED_NON_LABEL_EXPORTS` with the reason it
    carries no wording. "Everything else is a helper" is the category that grows
    in silence, which is why #206's exclusion set is pinned rather than derived
    and why this one is too — including the value lists and derived types, which
    an earlier draft matched by SHAPE. That rule was true of the nine present and
    would have been silently true of the tenth somebody added.
    """
    scanned, _ = legacy
    assert not scanned.unclassified, (
        f"unclassified exports of {ADAPTER}: {list(scanned.unclassified)}")
    assert set(DECLARED_NON_LABEL_EXPORTS) == {
        HUMANISER, "roleRank",
        "BILLING_MODES", "COSTING_METHODS", "PRODUCTS", "ROLES",
        "ANALYTICS_DIMENSIONS", "TIMESERIES_GROUP_BY", "WEBHOOK_EVENT_TYPES",
        "BillingMode", "Product", "Role",
    }, ("the declared non-label exports have changed. That is allowed, and it "
        "is a reviewable diff on purpose: each name here is a claim that the "
        "export carries no user-facing wording")


def test_the_adapter_gains_no_new_importer(legacy):
    """#210's other sentence: *new or modified code … may not reach the adapter*.

    The ledger owes each MAP, which bounds what the adapter still does. It does
    not bound who calls it — and every map falls back to the humaniser for a
    value it does not recognise, so ONE MORE importer spreads the retired
    behaviour without adding a single ledger entry. None of these files is a
    separate debt (each imports a map somebody already owes), so they are pinned
    here rather than seeded as one entry per importing file — which would have
    doubled the ledger and cleared at exactly the same moment. The live count is
    the pin below; restating it in prose is what goes stale.

    It is a RATCHET, not a target: the set may only shrink. Converting a file to
    `@/lib/localisation` means deleting its line, which is the diff that shows
    the work happened.
    """
    scanned, _ = legacy
    observed, pinned = set(scanned.importers), set(ADAPTER_IMPORTERS)
    added = sorted(observed - pinned)
    gone = sorted(pinned - observed)

    assert not added, (
        "these files newly import the legacy label adapter:\n  "
        + "\n  ".join(added)
        + f"\nUse `@/lib/localisation` instead. If this import is genuinely "
          f"unavoidable, adding it here is an explicit, reviewed act.")
    assert not gone, (
        "these files no longer import the legacy adapter — delete their lines "
        "from ADAPTER_IMPORTERS, so the count keeps meaning what it says:\n  "
        + "\n  ".join(gone))


def test_the_map_constructor_name_appears_nowhere_else():
    """The scanner takes the set of hand-written maps by matching
    `legacyLabelMap(`. #210 renamed it from the bare `label` for exactly this
    reason: `label` appears in this console as a prop, a variable and a string,
    so a gate keyed on it would be a gate keyed on a coincidence. This asserts
    the new name stayed unambiguous."""
    elsewhere = [
        path.relative_to(REPO_ROOT).as_posix()
        for path in sorted((REPO_ROOT / CONSOLE_ROOT).rglob("*.ts*"))
        if path.relative_to(REPO_ROOT).as_posix() != ADAPTER
        and MAP_CONSTRUCTOR in path.read_text(encoding="utf-8")
    ]
    assert not elsewhere, (
        f"`{MAP_CONSTRUCTOR}` is meant to name one private function in "
        f"{ADAPTER}; it also appears in {elsewhere}")


# ---------------------------------------------------------------------------
# 4. A debt this gate has already collected does not come back
# ---------------------------------------------------------------------------

#: The two humanising renderers slice 2 removed, each under the id of the ledger
#: entry that owed it (#279). Both rendered a value the TENANT authored — an
#: Event Type key, a metadata key — and ADR-0008 §4.4 is explicit that such a
#: value renders as the tenant declared it. Title-casing someone else's
#: identifier is the same defect as inventing UBB's own, and worse in one way:
#: it does not merely guess at a name UBB never wrote down, it overwrites one
#: the tenant did.
#:
#: This is NOT a second copy of the allowlist — the whole point of section 3 is
#: that the ledger IS the allowlist, and a constant restating live entries would
#: be the drifting copy ADR-0006 §4 warns about. These entries are not live.
#: They record a fact that is now permanent, which is exactly the class of thing
#: a literal may hold: two debts were paid, and neither side may quietly undo it.
PAID_HUMANISING_DEBTS = {
    "g6-humanises-test-event-response":
        "apps/ui/src/features/developers/components/test-event-response.tsx::humanize",
    "g6-humanises-metadata-tree":
        "apps/ui/src/features/settings/components/metadata-tree.tsx::humanize",
}


def test_a_paid_humanising_debt_names_a_file_that_still_exists(legacy):
    """Vacuity guard for section 4.

    The assertions below are absences, and an absence is trivially true of a
    file that has been deleted or renamed — at which point they would go on
    passing while proving nothing about any code that ships. Both components are
    still here; what changed is what they do.
    """
    assert PAID_HUMANISING_DEBTS, "nothing pinned — section 4 proves nothing"
    scanned, _ = legacy
    for site in sorted(PAID_HUMANISING_DEBTS.values()):
        path, _, function = site.partition("::")
        assert function == HUMANISER, f"`{site}` is not a humanising site"
        assert (REPO_ROOT / path).is_file(), (
            f"`{path}` no longer exists, so the absence below is vacuous. If the "
            f"component was genuinely removed, delete its line here and say so")
    # And the scan that reports the absence is not itself blind — section 3 asserts
    # this too, for the other half of the same reason.
    assert scanned.humanisers, "no humanising site found anywhere — the scan is blind"


def test_neither_paid_humanising_debt_has_come_back(legacy, programme):
    """The two encodings of a paid debt, held to each other by id (#279).

    `tests/contracts/test_model_naming_ledger_agreement.py` is the pattern: two
    encodings of one fact, compared by id and in BOTH directions, so that
    neither can gain, lose or relabel an entry alone. There the fact is a live
    suppression; here it is a collected debt, and the two sides are the ledger
    and the console rather than two files.

    Section 3 already refuses a humanising site with no ledger entry, and a
    ledger entry with no humanising site. What it cannot see is the pair moving
    together — an entry re-seeded and a `humanize` import restored in one change
    agree with each other perfectly, and the set comparison passes. That is the
    only shape in which this ticket's work silently reverts, so it is the shape
    this test is about.

    BOTH GATES/ FILES ARE ONE SIDE HERE, debts and permanent exceptions
    together. The quietest way to bring one of these back is not a ledger entry
    at all — it is an exception saying the humanising is permanent, which no
    ratchet counts and no slice ever clears.
    """
    scanned, _ = legacy
    excused = (*programme.entries, *programme.exceptions)
    faults = revivals(PAID_HUMANISING_DEBTS,
                      {record.id for record in excused},
                      recorded(programme, GATE) | excepted(programme, GATE),
                      set(scanned.humanisers))
    assert not faults, "a paid humanising debt is back.\n  " + "\n  ".join(faults)


# ---------------------------------------------------------------------------
# The predicates the assertions above call
# ---------------------------------------------------------------------------

def revivals(paid, ledger_ids, ledger_sites, humanising):
    """Every way a collected humanising debt could return, by id and by site.

    A real predicate rather than three inline `assert … not in`, so the controls
    below can push synthetic revivals through the function the assertion calls.

    THE ID IS THE IDENTITY AND THE SITE IS THE FALLBACK, which is why the ledger
    is asked about them in that order rather than both at once. The id alone
    would miss the same debt re-seeded under a new name — a rename away from
    invisible. Reporting both when both hold would say "under some id other than
    this one" about an entry carrying exactly this one, so the site is only
    reported when the id did not already account for it.
    """
    faults = []
    for entry_id, site in sorted(paid.items()):
        if entry_id in ledger_ids:
            faults.append(f"`{entry_id}` is recorded in gates/ again. It was "
                          f"paid, not deferred — re-seeding it needs the "
                          f"reasoning that says why, not a ledger line")
        elif site in ledger_sites:
            faults.append(f"{site} is excused in gates/ again under a different "
                          f"id — the same debt renamed is the same debt, and a "
                          f"reader following `{entry_id}` would find nothing")
        if site in humanising:
            faults.append(f"{site} reaches the humaniser again. A value the "
                          f"tenant authored renders as they declared it "
                          f"(ADR-0008 §4.4); UBB does not reword it")
    return faults


def recorded(programme, gate):
    """The sites the ledger records against a gate."""
    return {entry.site for entry in programme.entries if entry.gate == gate}


def excepted(programme, gate):
    """The sites the permanent exceptions excuse — accounted for, and not debts."""
    return {record.site for record in programme.exceptions if record.gate == gate}


def disagreements(observed, ledgered, excused=frozenset()):
    """Every way the tree and `gates/` fail to say the same thing.

    A real predicate rather than an inline `==`, so the controls below can push
    synthetic triples through the function the assertions actually use.
    Comparing two values derived from one source is a check that cannot fail,
    and this repository has shipped three of those.

    An observed site must be accounted for by EXACTLY ONE list, which is why
    both are inputs here rather than one comparison per list: an exception
    excuses a site from being a debt, not from being seen.
    """
    faults = []
    for site in sorted(observed - ledgered - excused):
        faults.append(f"{site} still hand-writes or humanises a label and no "
                      f"ledger entry owes it — a debt with no owner, invisible "
                      f"to the ratchet")
    for site in sorted(ledgered - observed):
        faults.append(f"{site} is recorded as a debt and the console no longer "
                      f"does it — the entry is unreachable and keeps the ledger "
                      f"off zero")
    return faults


# ---------------------------------------------------------------------------
# Negative controls — the reader flags what it is shown.
#
# Without these every assertion above could be structurally incapable of
# failing, which is the defect this whole directory exists to prevent.
# ---------------------------------------------------------------------------

def catalogue_of(entries, name=DEFAULT_LOCALE):
    """A synthetic single-locale catalogue, in the shape `read_catalogue` returns."""
    return Catalogue((Locale(name, f"{LOCALES_DIR}/{name}.json", dict(entries)),))


@pytest.fixture
def synthetic(tmp_path):
    """A registry with one closed concept, two values and one retired word."""
    return load(tmp_path, concepts={"synthetic.yaml": {"widget_state": concept(
        values=["idle", "spinning"],
        label_key_prefix="widget_state",
        retired_aliases=["whirring"],
    )}})


def test_negative_control_a_value_with_no_wording_is_flagged(synthetic):
    findings = coverage_faults(required_keys(synthetic),
                               catalogue_of({"widget_state.idle": "Idle"}),
                               synthetic)
    assert [finding.code for finding in findings] == [codes.UNLABELLED_VALUE]
    assert "widget_state.spinning" in findings[0].location


def test_negative_control_a_key_naming_nothing_is_flagged(synthetic):
    findings = coverage_faults(
        required_keys(synthetic),
        catalogue_of({"widget_state.idle": "Idle",
                      "widget_state.spinning": "Spinning",
                      "widget_state.melted": "Melted"}),
        synthetic)
    assert [finding.code for finding in findings] == [codes.UNKNOWN_KEY]


def test_negative_control_a_retired_token_that_kept_its_wording_is_flagged(synthetic):
    catalogue = catalogue_of({"widget_state.idle": "Idle",
                              "widget_state.spinning": "Spinning",
                              "widget_state.whirring": "Whirring"})
    findings = coverage_faults(required_keys(synthetic), catalogue, synthetic)

    assert [finding.code for finding in findings] == [codes.RETIRED_KEY]
    # And the independent statement of the same promise, which is the one that
    # has to keep working if the equality above is ever narrowed.
    assert retired_labels(catalogue, synthetic) == [
        ("widget_state.whirring", "whirring", "widget_state")]


def test_negative_control_a_blank_label_is_flagged(synthetic):
    findings = coverage_faults(
        required_keys(synthetic),
        catalogue_of({"widget_state.idle": "Idle", "widget_state.spinning": "  "}),
        synthetic)
    assert [finding.code for finding in findings] == [codes.BLANK_LABEL]


def test_negative_control_a_locale_missing_a_key_is_flagged(synthetic):
    """The four promises are stated per locale, so a complete `en` beside a
    half-translated one must fail. Today's single-locale tree cannot show
    this — which is why the control supplies a second locale."""
    complete = {"widget_state.idle": "Idle", "widget_state.spinning": "Spinning"}
    catalogue = Catalogue((
        Locale("en", f"{LOCALES_DIR}/en.json", dict(complete)),
        Locale("fr", f"{LOCALES_DIR}/fr.json", {"widget_state.idle": "Au repos"}),
    ))
    findings = coverage_faults(required_keys(synthetic), catalogue, synthetic)

    assert [finding.code for finding in findings] == [codes.UNLABELLED_VALUE]
    assert "fr.json" in findings[0].location


def test_positive_control_a_complete_catalogue_produces_no_findings(synthetic):
    assert coverage_faults(
        required_keys(synthetic),
        catalogue_of({"widget_state.idle": "Idle",
                      "widget_state.spinning": "Spinning"}),
        synthetic) == []


def test_negative_control_a_tenant_defined_concept_requires_no_wording(tmp_path):
    """map #137 constraint 5 as a checked rule: UBB never enumerates what the
    tenant owns, so it has no wording to supply either. A required key here
    would be the catalogue quietly becoming the vendor catalogue."""
    registry = load(tmp_path, concepts={"synthetic.yaml": {
        "widget_key": concept(kind="tenant_defined", values=ABSENT,
                              label_key_prefix=ABSENT),
    }})
    assert registry.concepts["widget_key"].kind == "tenant_defined"
    assert required_keys(registry) == {}


def test_negative_control_an_unrecorded_site_is_flagged():
    faults = disagreements({"apps/ui/src/x.tsx::humanize"}, set())
    assert len(faults) == 1 and "no ledger entry owes it" in faults[0]


def test_negative_control_an_unreachable_entry_is_flagged():
    faults = disagreements(set(), {"apps/ui/src/x.tsx::humanize"})
    assert len(faults) == 1 and "the entry is unreachable" in faults[0]


def test_positive_control_two_sides_that_agree_produce_no_faults():
    sites = {"apps/ui/src/x.tsx::humanize"}
    assert disagreements(sites, set(sites)) == []


def test_a_permanently_excepted_site_is_accounted_for_without_being_a_debt():
    """The one thing the exceptions list buys, and its limit: it accounts for a
    site, and it does not make the site invisible. A site in neither list still
    fails — which is what stops "add an exception" becoming the cheap way past
    this gate."""
    stripe = "apps/ui/src/lib/labels.ts::subscriptionStatusLabel"
    assert disagreements({stripe}, set(), excused={stripe}) == []
    assert len(disagreements({stripe, "apps/ui/src/x.tsx::humanize"}, set(),
                             excused={stripe})) == 1


# --- controls over a paid debt coming back (section 4) ----------------------

PAID = {"g6-humanises-x": "apps/ui/src/x.tsx::humanize"}


def test_negative_control_a_re_seeded_ledger_entry_is_flagged():
    """The id returns. This is the half a set comparison of sites cannot see,
    because a re-seeded entry and a restored import agree with each other."""
    faults = revivals(PAID, {"g6-humanises-x"}, set(), set())
    assert len(faults) == 1 and "paid, not deferred" in faults[0]


def test_negative_control_the_same_site_re_seeded_under_a_new_id_is_flagged():
    """The rename that an id-only check would miss. The debt is the site; the id
    is how a reader finds it, and changing one does not retire the other."""
    faults = revivals(PAID, {"g6-something-else"},
                      {"apps/ui/src/x.tsx::humanize"}, set())
    assert len(faults) == 1 and "under a different id" in faults[0]


def test_negative_control_a_restored_humaniser_is_flagged():
    """The console side. Reached through the same predicate as the two above, so
    a change that reverted both would report both rather than the first."""
    faults = revivals(PAID, set(), set(), {"apps/ui/src/x.tsx::humanize"})
    assert len(faults) == 1 and "reaches the humaniser again" in faults[0]


def test_negative_control_a_debt_restored_on_both_sides_at_once_is_flagged():
    """The shape section 3 is structurally incapable of catching, stated as its
    own control: the ledger and the console reverted together, agreeing
    perfectly. Two faults, not one — each side is named."""
    faults = revivals(PAID, {"g6-humanises-x"}, set(),
                      {"apps/ui/src/x.tsx::humanize"})
    assert len(faults) == 2


def test_positive_control_a_paid_debt_absent_from_both_sides_produces_no_faults():
    assert revivals(PAID, {"g6-unrelated"}, {"apps/ui/src/y.tsx::humanize"},
                    {"apps/ui/src/y.tsx::humanize"}) == []


# --- controls over reading the catalogue at all -----------------------------

def write_locales(tmp_path, *, index=None, files):
    """A synthetic console tree, loaded through the entry point CI calls."""
    directory = tmp_path / LOCALES_DIR
    directory.mkdir(parents=True)
    for name, body in files.items():
        (directory / name).write_text(
            body if isinstance(body, str) else json.dumps(body),
            encoding="utf-8")
    if index is not None:
        (directory / "index.ts").write_text(index, encoding="utf-8")
    return read_catalogue(tmp_path)


def only(faults):
    assert len(faults) == 1, [str(fault) for fault in faults]
    return faults[0].code


def test_negative_control_a_missing_locales_directory_is_a_fault(tmp_path):
    _, faults = read_catalogue(tmp_path)
    assert only(faults) == codes.LOCALES_MISSING


def test_negative_control_a_missing_index_is_a_fault(tmp_path):
    _, faults = write_locales(tmp_path, files={"en.json": {}})
    assert only(faults) == codes.INDEX_MISSING


def test_negative_control_a_catalogue_nobody_imports_is_a_fault(tmp_path):
    """It would ship to nobody while satisfying every coverage assertion above,
    because the union of loaded locales would never contain it."""
    _, faults = write_locales(
        tmp_path,
        index='import en from "./en.json";\n',
        files={"en.json": {}, "fr.json": {}})
    assert only(faults) == codes.LOCALE_UNDECLARED


def test_negative_control_an_import_with_no_catalogue_is_a_fault(tmp_path):
    catalogue, faults = write_locales(
        tmp_path,
        index='import en from "./en.json";\nimport fr from "./fr.json";\n',
        files={"en.json": {}})
    assert {fault.code for fault in faults} == {codes.LOCALE_MISSING}
    assert catalogue.locale("fr") is None


def test_negative_control_an_unparseable_catalogue_is_a_fault(tmp_path):
    _, faults = write_locales(tmp_path, index='import en from "./en.json";\n',
                              files={"en.json": "{oh dear"})
    assert codes.LOCALE_UNPARSEABLE in {fault.code for fault in faults}


def test_negative_control_a_repeated_key_is_a_fault(tmp_path):
    """JSON keeps the last silently, so one of two wordings ships and neither
    author knows which — the same default the registry loader refuses in YAML."""
    _, faults = write_locales(
        tmp_path, index='import en from "./en.json";\n',
        files={"en.json": '{"a.b": "One", "a.b": "Two"}'})
    assert codes.LOCALE_MALFORMED in {fault.code for fault in faults}


def test_negative_control_a_non_string_wording_is_a_fault(tmp_path):
    _, faults = write_locales(tmp_path, index='import en from "./en.json";\n',
                              files={"en.json": {"a.b": {"nested": "no"}}})
    assert codes.LOCALE_MALFORMED in {fault.code for fault in faults}


def test_negative_control_no_default_locale_is_a_fault(tmp_path):
    _, faults = write_locales(tmp_path, index='import fr from "./fr.json";\n',
                              files={"fr.json": {}})
    assert codes.DEFAULT_LOCALE_MISSING in {fault.code for fault in faults}


def test_positive_control_a_declared_locale_loads(tmp_path):
    catalogue, faults = write_locales(
        tmp_path, index='import en from "./en.json";\n',
        files={"en.json": {"a.b": "One"}})
    assert not faults
    assert catalogue.keys == {"a.b"}


# --- controls over scanning the adapter -------------------------------------

def write_console(tmp_path, *, adapter, others=()):
    (tmp_path / ADAPTER).parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / ADAPTER).write_text(adapter, encoding="utf-8")
    for name, body in others:
        path = tmp_path / CONSOLE_ROOT / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    return scan_legacy(tmp_path)


ADAPTER_SOURCE = f"""\
export function {HUMANISER}(value: string): string {{ return value; }}

function {MAP_CONSTRUCTOR}(map: Record<string, string>) {{ return map; }}

export const widgetStateLabel = {MAP_CONSTRUCTOR}({{ idle: "Idle" }});

export function roleRank(role: string): number {{ return role.length; }}
"""


def test_negative_control_a_missing_adapter_is_a_fault(tmp_path):
    scanned, faults = scan_legacy(tmp_path)
    assert only(faults) == codes.ADAPTER_MISSING
    assert scanned.sites == ()


def test_a_synthetic_adapter_scans_to_its_own_map(tmp_path):
    """The positive control the two below are measured against."""
    scanned, faults = write_console(tmp_path, adapter=ADAPTER_SOURCE)
    assert not faults
    assert scanned.sites == (f"{ADAPTER}::widgetStateLabel",)


def test_negative_control_an_unclassified_export_is_a_fault(tmp_path):
    scanned, faults = write_console(
        tmp_path,
        adapter=ADAPTER_SOURCE + "\nexport const prettyStatus = (s: string) => s;\n")
    assert only(faults) == codes.ADAPTER_ESCAPED
    assert scanned.unclassified == ("prettyStatus",)


def test_negative_control_a_privately_built_map_is_a_fault(tmp_path):
    """The classification reads `export const X = legacyLabelMap(`. A map built
    without that prefix and exported through a clause would be a hand-written
    value map the ledger never hears about — a debt with no owner, which is the
    one thing this gate exists to refuse."""
    scanned, faults = write_console(
        tmp_path,
        adapter=ADAPTER_SOURCE
        + f"\nconst sneakyLabel = {MAP_CONSTRUCTOR}({{ a: \"A\" }});\n")
    assert only(faults) == codes.ADAPTER_ESCAPED
    assert f"{ADAPTER}::sneakyLabel" not in scanned.sites


def test_negative_control_an_export_clause_is_a_fault(tmp_path):
    _, faults = write_console(
        tmp_path, adapter=ADAPTER_SOURCE + "\nexport { roleRank as rank };\n")
    assert only(faults) == codes.ADAPTER_ESCAPED


def test_negative_control_a_second_humaniser_is_a_fault(tmp_path):
    _, faults = write_console(
        tmp_path, adapter=ADAPTER_SOURCE,
        others=[("features/x.ts",
                 f"export function {HUMANISER}(v: string) {{ return v; }}\n")])
    assert only(faults) == codes.ADAPTER_ESCAPED


def test_a_file_importing_the_humaniser_becomes_a_site(tmp_path):
    scanned, faults = write_console(
        tmp_path, adapter=ADAPTER_SOURCE,
        others=[("features/x.ts",
                 f'import {{ {HUMANISER}, other }} from "{ADAPTER_SPECIFIER}";\n')])
    assert not faults
    assert f"{CONSOLE_ROOT}/features/x.ts::{HUMANISER}" in scanned.sites


def test_a_single_quoted_import_is_seen_too(tmp_path):
    """The console's eslint declares no `quotes` rule, so `'…'` is lint-clean.
    A `"`-only pattern would have made the whole allowlist optional."""
    scanned, faults = write_console(
        tmp_path, adapter=ADAPTER_SOURCE,
        others=[("features/x.ts",
                 f"import {{ {HUMANISER} }} from '{ADAPTER_SPECIFIER}';\n")])
    assert not faults
    assert f"{CONSOLE_ROOT}/features/x.ts::{HUMANISER}" in scanned.sites


def test_a_namespace_import_counts_as_reaching_the_humaniser(tmp_path):
    """`import * as labels` reaches every export, so the gate cannot tell
    whether the humaniser is used and must assume it is. Conservative in the
    only direction that is safe."""
    scanned, faults = write_console(
        tmp_path, adapter=ADAPTER_SOURCE,
        others=[("features/x.ts",
                 f'import * as labels from "{ADAPTER_SPECIFIER}";\n')])
    assert not faults
    assert f"{CONSOLE_ROOT}/features/x.ts::{HUMANISER}" in scanned.sites


def test_a_re_export_of_the_humaniser_is_a_site(tmp_path):
    """`export { humanize } from …` hands the retired behaviour to files that
    never name the adapter at all."""
    scanned, _ = write_console(
        tmp_path, adapter=ADAPTER_SOURCE,
        others=[("features/x.ts",
                 f'export {{ {HUMANISER} }} from "{ADAPTER_SPECIFIER}";\n')])
    assert f"{CONSOLE_ROOT}/features/x.ts::{HUMANISER}" in scanned.sites


def test_a_file_importing_something_else_is_an_importer_but_not_a_site(tmp_path):
    """The two questions, and the reason both are asked.

    Importing a map is not humanising, so the file is not a ledgered site —
    #210 is explicit that rewriting the fifty-one importers is not slice 0's
    job. But the map it imports still falls back to the humaniser, so the file
    IS an importer, and the pinned set is what stops another appearing.
    """
    scanned, faults = write_console(
        tmp_path, adapter=ADAPTER_SOURCE,
        others=[("features/x.ts",
                 f'import {{ widgetStateLabel }} from "{ADAPTER_SPECIFIER}";\n')])
    assert not faults
    assert scanned.humanisers == ()
    assert scanned.importers == (f"{CONSOLE_ROOT}/features/x.ts",)
