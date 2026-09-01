"""The four model-naming gates — ADR-0006 §§1, 3, 4 and 9 (#203, slice 0 — #191).

Four of ADR-0006's naming rules stop being prose here. They are installed
**while the codebase still violates them**, and that ordering is the point: a
gate installed before the code complies is what makes the vocabulary impossible
to regress (#155 §3.1). Today's violations are seeded into
``gates/migration-ledger.yaml``, each owed by the slice that removes it, and the
ledger only ever shrinks.

| Gate | Rule | ADR-0006 |
|---|---|---|
| G9  | A physical table name tracks its model name | §9 |
| G10 | A derived fact is not stored independently | §4 |
| G11 | A suffix names a unit, and two units may never share one | §1 |
| G12 | Method, mode and structure describe different things | §3 |

These live in the platform suite rather than the repository-wide contract suite
because their subject is the model layer: they read the Django app registry, and
a rule about ``db_table`` and field types has no honest source other than the
loaded models. ``test_product_boundaries.py`` sets the house pattern next door,
and this follows it — walk everything, classify with a pure function, and prove
the classifier bites with negative controls.

**What the classifiers can and cannot see.** Each is a pure function over one
``ModelFact``, so a negative control builds a real Django model under
``isolate_apps`` and pushes it through the same entry point the registry walk
uses. What none of them can settle is whether a legally-named field means what
its name claims — ADR-0008 §9's limit, restated: a green board proves the
declared invariants passed, not that the declarations are worth making. G11 in
particular catches a second unit **named in the field's own name**, which is the
shape the one real ambiguity took; a ``_micros`` column silently holding seconds
under a money-shaped name is invisible to it and belongs to review.

**Scope is the structural half** — names, field types and table names, which
need no registry content. Whether a ``method`` or ``mode`` field's *values*
match the vocabulary registry is G2's job and rides its consumers (#207).
"""

import re
from dataclasses import dataclass
from pathlib import Path

from django.apps import apps
from django.db import models
from django.test.utils import isolate_apps

ADR = "docs/adr/0006-domain-vocabulary-and-contract-naming.md"
LEDGER = "gates/migration-ledger.yaml"
EXCEPTIONS = "gates/permanent-exceptions.yaml"

# apps/platform/tests/test_model_naming.py -> the git root.
REPO_ROOT = Path(__file__).resolve().parents[4]

# Every first-party app is a package under `apps.`; the platform's own tree sits
# under `ubb-platform/` in the repository, which is what makes a site string
# here paste-able into a grep from the git root — and the ledger's `site` is
# read from the git root.
#
# Named `PLATFORM_TREE` rather than `PLATFORM_ROOT` on purpose: the module next
# door binds `PLATFORM_ROOT` to a `Path` at that directory, and two names alike
# in one package holding different types is the confusion this file's own G12
# rule exists to refuse.
FIRST_PARTY_PACKAGE = "apps."
PLATFORM_TREE = "ubb-platform"

TABLE_PREFIX = "ubb_"

# PostgreSQL truncates an identifier past this, silently colliding two tables
# whose names agree in the first 63 characters. #154 §6.4 ran this as a
# pre-flight check before adopting the rule; it stays as a test because the rule
# now *demands* a name, and demanding one the database cannot hold would be a
# gate with no legal answer.
IDENTIFIER_LIMIT = 63

# --- G10 -------------------------------------------------------------------
# The facts ADR-0006 §4 says are derived and must never be stored. Each may be
# *served* read-only so callers need not reconstruct the derivation, and a
# property or a serializer field does exactly that without becoming a column.
# This gate is about columns.
#
# `tenant_posture` is derived from `customer_billing_mode`.
#
# `measurements_status` (#271) is derived from a posting's own kind and from
# whether its measurement record is there — the registry declares that rule as
# `value_semantics` and the compiler proves it total. It joined this gate
# rather than arriving with an absence check of its own because the claim is
# identical and the subject is the same one: every column of every model in the
# app registry. A second mechanism asserting the same absence over the same
# walk would be two encodings of one gate, which is the shape §4 is about.
DERIVED_NEVER_STORED = frozenset({"tenant_posture", "measurements_status"})

# --- G11 -------------------------------------------------------------------
MONEY_SUFFIX = "_micros"

# Units that are not money. A `_micros` field naming one of these declares two
# units at once, which is the ambiguity ADR-0006 §1 exists to end — and it is
# not hypothetical: #147 §9.2 records that the `le=1_000_000_000` bound was
# added specifically because such a value "is far more likely a unit error
# (percent passed as micros) than a real commercial term".
#
# Every word here is a unit and only a unit. The singular `second` is
# deliberately absent: `LiveBalanceRepair.second_deficit_micros` is an ordinal —
# the second of two measurements — and a gate that condemns correct code is a
# gate people delete. Plural `seconds` is the duration suffix ADR-0006 §1 names,
# and no ordinal reads that way.
NON_MONEY_UNIT_WORDS = frozenset({
    "percent", "percentage", "pct", "permille", "bps",
    "seconds", "millis", "milliseconds",
    "bytes", "ratio",
})

# Money is an exact whole number of micros (`core/money.py`), so a money column
# is an integer column wide enough to hold one. The 32-bit fields are excluded
# deliberately rather than forgotten: `IntegerField` caps at ~2_147 currency
# units in micros, which is not a money column, it is a bug waiting for a large
# invoice.
MONEY_FIELD_TYPES = frozenset({"BigIntegerField", "PositiveBigIntegerField"})

# --- G12 -------------------------------------------------------------------
# The three words, and the names ADR-0006 §3 spells with them. The sanctioned
# names are the comparison set for the near-miss rule below, so this gate reads
# the ADR rather than inventing a vocabulary of its own.
SANCTIONED_WORDS = ("method", "mode", "structure")
SANCTIONED_NAMES = (
    "costing_method", "pricing_method",          # how an amount is derived
    "pricing_mode", "customer_billing_mode",      # which operating regime applies
    "rate_structure",                             # the shape of a rate
)

# Django's own noun. ADR-0006 §7: where a framework's word collides with a
# domain word, the framework yields — so a field may not be named for the thing
# it is declared on. A rate's arithmetic shape is `rate_structure` (#151 §13.2).
FRAMEWORK_WORDS = frozenset({"model", "models"})

RULE_TABLE = "table-name-tracks-model-name"        # G9
RULE_DERIVED = "derived-fact-is-not-stored"        # G10
RULE_MICROS = "micros-suffix-names-money-only"     # G11
RULE_ENUM_WORD = "method-mode-structure"           # G12

GATE_OF_RULE = {
    RULE_TABLE: "G9",
    RULE_DERIVED: "G10",
    RULE_MICROS: "G11",
    RULE_ENUM_WORD: "G12",
}

# ---------------------------------------------------------------------------
# Today's violations, seeded — the ledger's entries and the one exception.
#
# Both mirror `gates/`, keyed by the ledger's own `site` spelling and carrying
# `(entry id, found)`, and `tests/contracts/test_model_naming_ledger_agreement.py`
# holds the two encodings to each other in both directions. They cannot live in
# one place: this suite has no PyYAML (the platform lock deliberately does not
# carry it) and the contract suite has no Django (deliberately, so a Django
# import creeping in would be caught). Two encodings of one fact is exactly what
# ADR-0006 §4 warns about, so the agreement test is not optional decoration —
# it is what makes this list a copy rather than a second opinion.
#
# The alternative considered and rejected: GENERATE this list from the ledger,
# the way `core/vocabulary.py` is generated from the registry (#200), with a
# zero-diff gate. That is the house answer for registry VALUES in backend code
# (docs/conventions/coding-standards.md), and it does not fit here — it would
# put a generated artifact inside a test package and make `tools/vocabulary`'s
# generator own a `gates/` artifact, crossing the boundary #198 and #201 drew
# between the two programmes. The agreement test buys the same guarantee — they
# cannot disagree — for a fraction of the machinery.
#
# An entry here is a debt, not an excuse. `test_every_seeded_entry_is_still_a_
# real_violation` fails the moment a seeded site is fixed and the entry is not
# deleted, so the ledger cannot rot into an allowlist nobody rereads.
# ---------------------------------------------------------------------------

# Spelled as plain literals rather than built from `PLATFORM_TREE`, for two
# reasons: a site is then greppable verbatim across this file and `gates/`, and
# the agreement test can read these with `ast.literal_eval` without importing
# Django into a suite that deliberately has none.
LEDGERED_VIOLATIONS = {
    "G9": {
        # ⚠ BOTH HALVES OF THE PRICING INVERSION ARE PAID AND GONE — the rule's
        # in #367, the container's in #368 — and this gate now owes nothing in
        # that app. The rule sat on the table named for the container beside
        # it and moved to the table its own name asks for; the container was
        # not renamed onto the name it had lent out, because it SPLIT: a
        # Pricing Book and a cost book, on `ubb_pricing_book` and
        # `ubb_cost_book`, two entities whose columns disagree. Each entry was
        # deleted from the ledger and from here in the commit that discharged
        # it, which is what keeps paying a debt and recording the payment one
        # act.
        "ubb-platform/apps/subscriptions/models.py::CustomerSubscriptionItem":
            ("g9-customer-subscription-item-table-abbreviated",
             "ubb_customer_sub_item"),
    },
    # G11 IS EMPTY, AND BOTH ENTRIES WERE PAID BY DELETION RATHER THAN BY THE
    # RENAME THEIR `expected` COLUMN NAMED (#369). Two columns held millionths
    # of a PERCENT under the money suffix — one on the tenant-level markup
    # record, one on the kernel's Plan — and each entry's own `reason` said the
    # payment was the column going. A ticket reading only the `expected` value
    # would have renamed a column it was about to drop, and the honest spelling
    # would then have landed on a column with no reader left. It was taken
    # instead on `TenantDefaultMarkup.markup_micro_percent`, a NEW column where
    # it cost nothing (#357). Each entry was deleted from the ledger and from
    # here in the commit that discharged it, which is what keeps paying a debt
    # and recording the payment one act.
    "G11": {},
    # G12 IS EMPTY, AND EMPTY IS THE END STATE RATHER THAN AN OVERSIGHT (#366).
    # It held one entry: the rate's arithmetic-shape column, which sat one
    # character from `pricing_mode` and meant something unrelated — ADR-0006
    # §3's own worked example. The column is `rate_structure` now, so the entry
    # is deleted rather than left standing, which is the ledger's own rule: an
    # excuse that no longer describes a real violation overstates the debt.
    # A gate with nothing left to excuse is a gate that holds.
    "G12": {},
}

PERMANENT_EXCEPTIONS = {
    "G9": {
        "ubb-platform/apps/platform/tenants/models.py::ConnectOAuthState":
            "g9-connect-oauth-state-is-one-acronym",
    },
}


# ---------------------------------------------------------------------------
# The facts a rule is decided on
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FieldFact:
    """One concrete column: what it is called, and what it holds."""
    name: str
    internal_type: str


@dataclass(frozen=True)
class ModelFact:
    """One model, reduced to what the four rules actually read.

    Reduced on purpose. A classifier that took a model class could reach for
    anything — a manager, a related object, the database — and a negative
    control would then have to build a whole world to exercise one rule.
    """
    name: str
    app_label: str
    module: str
    db_table: str
    fields: tuple
    managed: bool
    proxy: bool

    @property
    def source(self):
        """The file the model is declared in, relative to the git root."""
        return f"{PLATFORM_TREE}/{self.module.replace('.', '/')}.py"

    @property
    def site(self):
        return f"{self.source}::{self.name}"

    def field_site(self, field):
        return f"{self.site}.{field.name}"


def model_facts(model):
    """Reduce a Django model class to the facts the rules read.

    ``concrete_fields`` rather than ``get_fields()`` is the whole of G10's
    "writable": a reverse relation is not a column, a many-to-many is a table of
    its own, and a ``@property`` serving a derived value is exactly what
    ADR-0006 §4 permits.
    """
    meta = model._meta
    return ModelFact(
        name=model.__name__,
        app_label=meta.app_label,
        module=model.__module__,
        db_table=meta.db_table,
        fields=tuple(FieldFact(field.name, field.get_internal_type())
                     for field in meta.concrete_fields),
        managed=meta.managed,
        proxy=meta.proxy,
    )


def first_party_models():
    """Every model declared by a UBB app.

    ``django.contrib`` and third-party tables are somebody else's vocabulary and
    somebody else's migrations; ADR-0006 §9 says so in as many words. Auto-created
    through tables are excluded by ``get_models()``'s own default, which is the
    right answer for the same reason.
    """
    return [model for model in apps.get_models()
            if model._meta.app_config is not None
            and model._meta.app_config.name.startswith(FIRST_PARTY_PACKAGE)]


# ---------------------------------------------------------------------------
# The four rules, as pure functions
# ---------------------------------------------------------------------------

def canonical_table(model_name):
    """``ubb_`` plus the mechanically snake-cased model name (ADR-0006 §9).

    Mechanical on purpose: a rule with a judgement step in it is not a gate.
    Where the mechanism produces a worse name than the one in place — an acronym
    is one token to a reader and several to a regular expression — the answer is
    a stated exception in ``gates/permanent-exceptions.yaml``, not a cleverer
    regular expression that nobody can predict.
    """
    return TABLE_PREFIX + re.sub(r"(?<!^)(?=[A-Z])", "_", model_name).lower()


def classify_table(fact):
    """G9 — ADR-0006 §9. Managed concrete first-party models only (#154 §6.4)."""
    if not fact.managed or fact.proxy:
        return None
    expected = canonical_table(fact.name)
    if fact.db_table == expected:
        return None
    return (
        RULE_TABLE, fact.site,
        f"{fact.site} sits on `{fact.db_table}`, not `{expected}` — a physical "
        f"table name tracks its model name, so the database does not preserve "
        f"obsolete terminology (ADR-0006 §9). A deliberate exception belongs in "
        f"{EXCEPTIONS} with its reason; a rename that is coming belongs in "
        f"{LEDGER} with the slice that does it — see {ADR}",
    )


def classify_derived(fact, field):
    """G10 — ADR-0006 §4. A derived fact is served, never stored."""
    if field.name not in DERIVED_NEVER_STORED:
        return None
    return (
        RULE_DERIVED, fact.field_site(field),
        f"{fact.field_site(field)} is a writable column for a DERIVED fact. "
        f"Two encodings of one fact can disagree, and the wrong one is always "
        f"the one nobody is looking at — serve it read-only from the field it "
        f"is derived from instead (ADR-0006 §4) — see {ADR}",
    )


def classify_micros(fact, field):
    """G11 — ADR-0006 §1. ``_micros`` means millionths of a currency unit."""
    if not field.name.endswith(MONEY_SUFFIX):
        return None

    second_unit = sorted(set(field.name.split("_")) & NON_MONEY_UNIT_WORDS)
    if second_unit:
        return (
            RULE_MICROS, fact.field_site(field),
            f"{fact.field_site(field)} carries the money suffix and names "
            f"`{second_unit[0]}` as well — two units may never share one "
            f"suffix. A percentage scaled by a million is `_micro_percent`, a "
            f"duration is `_seconds` (ADR-0006 §1) — see {ADR}",
        )

    if field.internal_type not in MONEY_FIELD_TYPES:
        return (
            RULE_MICROS, fact.field_site(field),
            f"{fact.field_site(field)} carries the money suffix but is a "
            f"{field.internal_type}. Money is an exact whole number of micros "
            f"(core/money.py), so a money column is one of "
            f"{', '.join(sorted(MONEY_FIELD_TYPES))} — see {ADR}",
        )
    return None


def classify_enum_word(fact, field):
    """G12 — ADR-0006 §3. Method, mode and structure describe different things.

    Two conjuncts. A name one character from a sanctioned name is the defect: it
    reads as a typo of a real concept while in fact naming something else, so a
    reader has no way to tell a mistake from a fourth word for an existing idea.

    ⚠ **THE ADR'S OWN WORKED EXAMPLE IS NOT SPELLED HERE, AND ITS ABSENCE IS THE
    GATE WORKING (#366).** The pair this rule was written for was the rate's
    arithmetic-shape column beside `pricing_mode`; that column is
    `rate_structure` now, its ledger entry is deleted, and the retired spelling
    has left the backend entirely — so writing it into this module would put a
    file back into an extent the sweep records as empty. ADR-0006 §3 still names
    the pair, because a document whose subject IS the retired vocabulary is
    allowed to; a test module is a living surface and is not. The controls below
    therefore drive the rule with other one-character pairs, which is what they
    were always testing.

    The comparison set is the five names ADR-0006 §3 spells, NOT an edit
    distance against the three bare words — ``code`` is one character from
    ``mode``, and ``status_code``, ``reason_code`` and ``referral_code`` are
    three perfectly good names that a distance rule would condemn. A rule that
    fires on correct code is not a stricter gate; it is a gate people delete.
    """
    if field.name in SANCTIONED_NAMES:
        return None

    near = [name for name in SANCTIONED_NAMES
            if _differs_by_one_character(field.name, name)]
    if near:
        return (
            RULE_ENUM_WORD, fact.field_site(field),
            f"{fact.field_site(field)} differs by one character from "
            f"`{near[0]}`, which means something else. Two names that close "
            f"with unrelated meanings are a defect, not a coincidence "
            f"(ADR-0006 §3) — see {ADR}",
        )

    word = field.name.rsplit("_", 1)[-1]
    if word in FRAMEWORK_WORDS:
        return (
            RULE_ENUM_WORD, fact.field_site(field),
            f"{fact.field_site(field)} names a field after Django's own noun. "
            f"Where a framework's word collides with a domain word the "
            f"framework yields (ADR-0006 §7); the three words for these fields "
            f"are {', '.join(SANCTIONED_WORDS)} (§3) — see {ADR}",
        )
    return None


def _differs_by_one_character(left, right):
    """One substitution, one insertion or one deletion apart — never equal."""
    if left == right or abs(len(left) - len(right)) > 1:
        return False
    if len(left) == len(right):
        return sum(a != b for a, b in zip(left, right)) == 1
    short, long = sorted((left, right), key=len)
    return any(long[:index] + long[index + 1:] == short
               for index in range(len(long)))


FIELD_RULES = (classify_derived, classify_micros, classify_enum_word)


def classify(fact):
    """Every rule ``fact`` violates, table rule first."""
    hits = []
    table = classify_table(fact)
    if table is not None:
        hits.append(table)
    for field in fact.fields:
        for rule in FIELD_RULES:
            hit = rule(fact, field)
            if hit is not None:
                hits.append(hit)
    return hits


# ---------------------------------------------------------------------------
# The walk
# ---------------------------------------------------------------------------

def _collect():
    """Walk the registry once; return (violations, facts)."""
    violations, facts = [], []
    for model in first_party_models():
        fact = model_facts(model)
        facts.append(fact)
        violations.extend(classify(fact))
    return violations, facts


_VIOLATIONS, _FACTS = _collect()


def _entry_id(entry):
    """A ledger entry is `(id, found)`; a permanent exception is just an id.

    The shapes differ because the two lists differ: the schema gives an
    exception no `expected` and no `found`, since no rename is coming and there
    is nothing for a later value to be compared against.
    """
    return entry[0] if isinstance(entry, tuple) else entry


def _excused(gate, site):
    return (site in LEDGERED_VIOLATIONS.get(gate, {})
            or site in PERMANENT_EXCEPTIONS.get(gate, {}))


def _failures(rule):
    """Everything this rule found that nothing in `gates/` accounts for."""
    gate = GATE_OF_RULE[rule]
    return "\n".join(message for found, site, message in _VIOLATIONS
                     if found == rule and not _excused(gate, site))


# ---------------------------------------------------------------------------
# The vacuity guards — this walked the codebase, and the seeds are still real
# ---------------------------------------------------------------------------

def test_walker_actually_sees_the_model_layer():
    """Guard against a green board from an empty walk.

    An app registry that failed to load, a package rename, or a filter that
    stopped matching would all produce zero models and four passing gates. The
    boundary walker next door counts modules and names five it must have
    visited; this counts models and does the same, one per product plus the
    kernel, so a whole app dropping out is caught rather than averaged away.
    """
    assert len(_FACTS) > 50, f"only walked {len(_FACTS)} models"

    columns = sum(len(fact.fields) for fact in _FACTS)
    assert columns > 300, f"only walked {columns} columns"

    # Named by APP rather than by model. Every model this walk covers is a
    # model some slice renames or deletes — naming `Rate` here would hand slice
    # 4 a test to edit for no reason, and a guard that has to be edited to stay
    # true is one that gets edited into meaninglessness. App labels are stable
    # across the re-model: it renames the domain, not the packages.
    apps_seen = {fact.app_label for fact in _FACTS}
    for expected in ("tenants", "work", "usage", "pricing", "wallets",
                     "subscriptions", "referrals"):
        assert expected in apps_seen, f"walker visited no model in `{expected}`"

    seen = {fact.name for fact in _FACTS}
    for expected in ("Tenant", "Task", "Posting", "Wallet"):
        assert expected in seen, f"walker did not visit {expected}"


def test_g10_has_a_derived_fact_to_protect():
    """G10's own vacuity guard, over the set rather than over the walk.

    The guard above proves the app registry was read; this proves the gate had
    something to look for in it. An empty `DERIVED_NEVER_STORED` would make
    G10 an assertion about nothing while every message about it stayed true,
    and each name must be a plain column name or the classifier could never
    meet it.
    """
    assert DERIVED_NEVER_STORED, "G10 protects no fact — it asserts nothing"
    for name in DERIVED_NEVER_STORED:
        assert name.islower() and name.isidentifier(), name


def test_the_derived_check_matches_the_whole_column_name():
    """A near miss is NOT flagged — driven through the real classifier.

    The counterpart to the negative control below, and it has to go through
    `classify` for the same reason that one does: a check written against the
    frozenset alone would be true by construction and would prove nothing about
    what the gate does to a column.

    `tenant_postures` and `measurements_status_at` are different columns, and
    an absence check that fires on names having nothing to do with it is one
    that gets suppressed rather than obeyed — which is the property the
    repository's other absence check pins for itself.
    """
    for name in sorted(DERIVED_NEVER_STORED):
        for near_miss in (f"{name}s", f"{name}_at", f"prior_{name}"):
            with isolate_apps(APP):
                widget = type("Widget", (models.Model,), {
                    "__module__": __name__,
                    near_miss: models.CharField(max_length=20),
                    "Meta": type("Meta", (), {"app_label": "tenants",
                                              "db_table": "ubb_widget"}),
                })
                assert not classify(model_facts(widget)), (
                    f"`{near_miss}` was flagged; only `{name}` is the derived "
                    f"fact, and a gate that condemns correct columns is one "
                    f"people delete")


def test_every_model_site_names_a_file_that_exists():
    """The `site` strings the ledger carries point at real files.

    A ledger entry is identified by its gate and its site. If the site spelling
    were wrong — a package that moved, a path built from the wrong root — every
    entry would be unfalsifiable and the allowlist would excuse nothing while
    looking like it excused something.
    """
    missing = sorted({fact.source for fact in _FACTS
                      if not (REPO_ROOT / fact.source).is_file()})
    assert not missing, "model source paths do not resolve:\n" + "\n".join(missing)


def test_every_seeded_entry_is_still_a_real_violation():
    """A seeded entry that is no longer a violation must be deleted, not kept.

    This is what stops the ledger rotting into an allowlist nobody rereads. When
    slice 4 rebuilds `Rate` on the right table, this test goes red until the
    entry is removed — so paying a debt and recording the payment are one act
    rather than two, the second of which gets forgotten.
    """
    found = {(GATE_OF_RULE[rule], site) for rule, site, _ in _VIOLATIONS}
    stale = sorted(
        f"{gate} {_entry_id(entry)} ({site})"
        for source in (LEDGERED_VIOLATIONS, PERMANENT_EXCEPTIONS)
        for gate, sites in source.items()
        for site, entry in sites.items()
        if (gate, site) not in found
    )
    assert not stale, (
        "these are recorded in gates/ but are no longer violations — delete "
        "them from the ledger (or the exceptions) and from this module:\n"
        + "\n".join(stale)
    )


def test_every_seeded_table_entry_still_names_the_table_it_recorded():
    """An excuse covers the violation recorded, not whatever the site does next.

    `_excused` keys on the gate and the site, which is the ledger's own notion of
    identity — and on its own that is too generous for G9. If a seeded model
    moved from the table its entry records to a THIRD wrong one, the site would
    still be excused, the gate would stay green, and the entry's `found:` would
    quietly become untrue. So the recorded `found` is checked against the live
    table.

    ⚠ The worked example used to be `Rate`, and that entry is PAID (#367): the
    rule sits on the table its own name asks for and the entry is deleted. What
    the example described is still exactly what this test refuses — it is the
    container's entry, and every other gate's, that it now guards.

    G11 and G12 need no equivalent: their sites end in the field name, so a
    field that changed its name changed its site, and the entry goes stale by
    the test above.
    """
    by_site = {fact.site: fact for fact in _FACTS}
    drifted = []
    for site, (identifier, recorded) in LEDGERED_VIOLATIONS["G9"].items():
        fact = by_site.get(site)
        assert fact is not None, f"{identifier}: no model at {site}"
        if fact.db_table != recorded:
            drifted.append(f"{identifier}: the ledger records "
                           f"found=`{recorded}`, the model is on "
                           f"`{fact.db_table}`")
    assert not drifted, (
        "a seeded table moved without the ledger being updated — the excuse "
        "covers a violation that no longer exists:\n" + "\n".join(drifted))


# ---------------------------------------------------------------------------
# The four gates
# ---------------------------------------------------------------------------

def test_table_name_is_the_canonical_snake_cased_model_name():
    """G9 — ADR-0006 §9."""
    assert not _failures(RULE_TABLE), "\n" + _failures(RULE_TABLE)


def columns_storing_a_derived_fact():
    """G10's own finding, for a caller outside this module (#418).

    Public for the reason `columns_the_database_does_not_defend` is: a product
    test whose subject is one derived fact has to be able to ask THE GATE
    whether that fact is still derived, rather than restate the claim with a
    walk of its own. Two copies of one search agreeing with each other proves
    nothing about either, and the copy is the one that goes quiet.

    Returns the gate's message text, empty when nothing is found — the same
    value the check below asserts on, so a caller and the gate cannot come to
    disagree about what a failure is.
    """
    return _failures(RULE_DERIVED)


def test_no_writable_column_stores_a_derived_fact():
    """G10 — ADR-0006 §4.

    Green in the tree today, which is why it ships with the negative control
    below: an absence test with nothing proving it can fail is a test that
    asserts nothing, and this repository has shipped that shape three times.
    The control is driven over every name in `DERIVED_NEVER_STORED`, so a fact
    added to the set is shown to be catchable rather than assumed to be.
    """
    assert not _failures(RULE_DERIVED), "\n" + _failures(RULE_DERIVED)


def test_the_micros_suffix_names_money_and_nothing_else():
    """G11 — ADR-0006 §1."""
    assert not _failures(RULE_MICROS), "\n" + _failures(RULE_MICROS)


def test_method_mode_and_structure_describe_different_things():
    """G12 — ADR-0006 §3."""
    assert not _failures(RULE_ENUM_WORD), "\n" + _failures(RULE_ENUM_WORD)


# ---------------------------------------------------------------------------
# #154 §6.4's two pre-flight checks
#
# Both were run by hand against `main` before the rule was adopted. They stay as
# tests because the rule now *demands* a canonical name: if two models canonicalise
# onto one table, or a canonical name is longer than the database can hold, the
# gate above would be asking for something impossible and the failure would look
# like a naming argument rather than a broken rule.
# ---------------------------------------------------------------------------

def test_canonical_table_names_do_not_collide():
    owners = {}
    collisions = []
    for fact in _FACTS:
        if not fact.managed or fact.proxy:
            continue
        canonical = canonical_table(fact.name)
        if canonical in owners:
            collisions.append(f"{fact.name} and {owners[canonical]} both "
                              f"canonicalise to `{canonical}`")
        owners[canonical] = fact.name
    assert not collisions, "\n" + "\n".join(collisions)


def test_canonical_table_names_fit_the_database_identifier_limit():
    too_long = sorted(
        f"{fact.name} -> {canonical_table(fact.name)} "
        f"({len(canonical_table(fact.name))} chars)"
        for fact in _FACTS
        if fact.managed and not fact.proxy
        and len(canonical_table(fact.name)) > IDENTIFIER_LIMIT
    )
    assert not too_long, (
        f"PostgreSQL truncates past {IDENTIFIER_LIMIT} characters:\n"
        + "\n".join(too_long))


# ---------------------------------------------------------------------------
# Negative controls — each gate fails on a synthetic violation.
#
# The models are REAL Django models, declared under `isolate_apps` so they get
# genuine `_meta` without joining the app registry or the migration state, and
# they go through `model_facts` — the same reduction the registry walk uses. A
# control that hand-built a `ModelFact` would prove the classifier works on the
# input the classifier expects, which is not the question.
# ---------------------------------------------------------------------------

APP = "apps.platform.tenants"


@isolate_apps(APP)
def test_negative_control_a_mismatched_table_is_flagged():
    class Widget(models.Model):
        class Meta:
            app_label = "tenants"
            db_table = "ubb_gadget"

    hit = classify_table(model_facts(Widget))
    assert hit is not None
    rule, site, message = hit
    assert rule == RULE_TABLE
    assert "`ubb_gadget`" in message and "`ubb_widget`" in message
    assert site.endswith("::Widget")


def test_negative_control_a_stored_derived_fact_is_flagged():
    """One control per derived fact, driven off the set itself.

    Written as a loop rather than as one control per name so that coverage is
    structural: a fact added to `DERIVED_NEVER_STORED` is exercised the moment
    it is added, and cannot arrive with a gate nobody has ever seen fail. Each
    iteration gets its own app registry, so the models do not collide.

    The whole hit list is compared, not just its first entry — a control that
    also tripped G9 or G11 would be evidence for the wrong rule.
    """
    for name in sorted(DERIVED_NEVER_STORED):
        with isolate_apps(APP):
            widget = type("Widget", (models.Model,), {
                # Django's metaclass reads this out of the attrs dict, and
                # `type()` does not supply it the way a `class` statement does.
                "__module__": __name__,
                name: models.CharField(max_length=20),
                "Meta": type("Meta", (), {"app_label": "tenants",
                                          "db_table": "ubb_widget"}),
            })
            hits = classify(model_facts(widget))
            assert [rule for rule, _, _ in hits] == [RULE_DERIVED], name
            assert "DERIVED" in hits[0][2], name
            assert hits[0][1].endswith(f"::Widget.{name}"), hits[0][1]


@isolate_apps(APP)
def test_negative_control_a_second_unit_under_the_money_suffix_is_flagged():
    class Widget(models.Model):
        markup_percentage_micros = models.BigIntegerField(default=0)

        class Meta:
            app_label = "tenants"
            db_table = "ubb_widget"

    hits = classify(model_facts(Widget))
    assert [rule for rule, _, _ in hits] == [RULE_MICROS]
    assert "percentage" in hits[0][2] and "_micro_percent" in hits[0][2]


@isolate_apps(APP)
def test_negative_control_a_money_suffix_on_a_non_money_type_is_flagged():
    class Widget(models.Model):
        # The suffix promises an exact whole number of millionths; a Decimal
        # column promises a scale of its own, and the two disagree silently.
        balance_micros = models.DecimalField(max_digits=20, decimal_places=6)

        class Meta:
            app_label = "tenants"
            db_table = "ubb_widget"

    hits = classify(model_facts(Widget))
    assert [rule for rule, _, _ in hits] == [RULE_MICROS]
    assert "DecimalField" in hits[0][2]


@isolate_apps(APP)
def test_negative_control_a_name_one_character_from_a_sanctioned_one_is_flagged():
    """The near-miss conjunct, driven by a plural of a sanctioned name.

    ⚠ It used to be driven by ADR-0006 §3's own example — the rate's
    arithmetic-shape column beside `pricing_mode` — and that spelling has left
    the backend with #366, so it is not written here (the module docstring for
    `classify_enum_word` says why). The pair below is the same defect in the
    same class: `rate_structures` is one insertion from `rate_structure`, names
    no concept the registry declares, and would read to any reviewer as the
    sanctioned name typed carelessly. The rule cannot tell that from a
    deliberate fourth word, which is exactly its point.
    """
    class Widget(models.Model):
        rate_structures = models.CharField(max_length=20)

        class Meta:
            app_label = "tenants"
            db_table = "ubb_widget"

    hits = classify(model_facts(Widget))
    assert [rule for rule, _, _ in hits] == [RULE_ENUM_WORD]
    assert "`rate_structure`" in hits[0][2]


@isolate_apps(APP)
def test_negative_control_the_framework_noun_is_flagged_on_its_own():
    """A `_model` field far from any sanctioned name is still a defect.

    Without this conjunct the gate would only ever catch the one collision
    ADR-0006 §3 already names, and `analytics_model` would sail through
    tomorrow.
    """
    class Widget(models.Model):
        analytics_model = models.CharField(max_length=20)

        class Meta:
            app_label = "tenants"
            db_table = "ubb_widget"

    hits = classify(model_facts(Widget))
    assert [rule for rule, _, _ in hits] == [RULE_ENUM_WORD]
    assert "Django's own noun" in hits[0][2]


@isolate_apps(APP)
def test_negative_control_an_unexcused_violation_reaches_the_gate():
    """The end-to-end shape: a violation nothing in `gates/` names must fail.

    The controls above prove the classifiers bite. This one proves the excusing
    step cannot swallow a violation it was never told about — the failure mode
    an allowlist actually has.
    """
    class Widget(models.Model):
        class Meta:
            app_label = "tenants"
            db_table = "ubb_gadget"

    rule, site, message = classify_table(model_facts(Widget))
    assert not _excused(GATE_OF_RULE[rule], site)


# ---------------------------------------------------------------------------
# Positive controls — a legal construction passes every rule.
# ---------------------------------------------------------------------------

@isolate_apps(APP)
def test_positive_control_a_legally_named_model_passes_every_rule():
    class WidgetSetting(models.Model):
        balance_micros = models.BigIntegerField(default=0)
        top_up_amount_micros = models.PositiveBigIntegerField(default=0)
        markup_micro_percent = models.BigIntegerField(default=0)
        retention_seconds = models.BigIntegerField(default=0)
        costing_method = models.CharField(max_length=20)
        customer_billing_mode = models.CharField(max_length=20)
        rate_structure = models.CharField(max_length=20)
        # A near-miss of `mode` that is a different word with its own meaning,
        # not a typo of a sanctioned name. It must pass.
        reason_code = models.CharField(max_length=40)

        class Meta:
            app_label = "tenants"
            db_table = "ubb_widget_setting"

    assert classify(model_facts(WidgetSetting)) == []


@isolate_apps(APP)
def test_positive_control_an_unmanaged_table_is_not_the_table_rule_s_business():
    """#154 §6.4 — the rule covers managed, concrete, first-party tables only.

    An unmanaged model maps a table UBB does not own, so demanding UBB's naming
    convention of it would be a rule about somebody else's database.
    """
    class ExternalReadModel(models.Model):
        class Meta:
            app_label = "tenants"
            db_table = "legacy_external_view"
            managed = False

    assert classify_table(model_facts(ExternalReadModel)) is None


def test_positive_control_the_canonical_form_is_the_mechanical_one():
    assert canonical_table("Rate") == "ubb_rate"
    assert canonical_table("PricingBook") == "ubb_pricing_book"
    assert canonical_table("CostBook") == "ubb_cost_book"
    assert canonical_table("CustomerSubscriptionItem") == (
        "ubb_customer_subscription_item")
    # The acronym case, spelled out: this is what the permanent exception in
    # gates/permanent-exceptions.yaml exists for, and why it is an exception
    # rather than a special case in `canonical_table`.
    assert canonical_table("ConnectOAuthState") == "ubb_connect_o_auth_state"


def test_positive_control_one_character_apart_is_not_a_prefix_match():
    assert _differs_by_one_character("rate_structures", "rate_structure")
    assert _differs_by_one_character("costing_methd", "costing_method")
    assert _differs_by_one_character("pricing_modes", "pricing_mode")
    # Equal is not "differs", and two characters is not one.
    assert not _differs_by_one_character("pricing_mode", "pricing_mode")
    assert not _differs_by_one_character("pricing_modelling", "pricing_mode")
    assert not _differs_by_one_character("reason_code", "pricing_mode")
