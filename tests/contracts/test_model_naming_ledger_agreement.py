"""The model-naming gates and `gates/` say the same thing (#203).

The four model-naming gates run in the platform suite, because their subject is
the Django app registry. The debts they excuse are recorded in
`gates/migration-ledger.yaml` and `gates/permanent-exceptions.yaml`, at the git
root. The two cannot be one file:

- the platform suite has no PyYAML — `ubb-platform/requirements.lock.txt` does
  not carry it, and the `test` job installs nothing else;
- this suite has no Django, deliberately, so that a Django import creeping in
  would be caught rather than silently work.

So the seeded sites exist twice, which is exactly the shape ADR-0006 §4 warns
about: two encodings of one fact can disagree, and the wrong one is always the
one nobody is looking at. Here the wrong one is worse than usual — a site
excused in the gate but absent from the ledger is a suppression with no debt
behind it, invisible to the ratchet and to slice 8's "every allowlist is at
zero".

This test is what makes the second encoding a copy rather than a second
opinion. It reads the gate's literals with `ast` — no import, no Django — and
holds them to the ledger in **both** directions, including the entry ids, so
neither file can gain, lose or relabel a site alone.
"""

import ast
from functools import lru_cache

import pytest

from _helpers import REPO_ROOT
from tools.gates import load_programme

GATES_DIR = REPO_ROOT / "gates"

GATE_MODULE = "ubb-platform/apps/platform/tests/test_model_naming.py"

#: The four gates that module installs. The comparison below is driven by the
#: UNION of what each side declares rather than by a list of the gates that
#: happen to be seeded today — a hardcoded list would silently exempt a gate
#: that gained its first entry later, which is precisely the gate whose seeding
#: nobody has reviewed yet.
MODEL_NAMING_GATES = ("G9", "G10", "G11", "G12")

LEDGER_CONSTANT = "LEDGERED_VIOLATIONS"
EXCEPTIONS_CONSTANT = "PERMANENT_EXCEPTIONS"


@lru_cache(maxsize=4)
def _parsed(source):
    """The gate module's AST, parsed once rather than once per lookup.

    The parse is cached, not the extracted value: `literal_eval` runs fresh on
    every call, so no caller can hand another a dict it has already mutated.
    """
    return ast.parse(source)


def literal_constant(source, name):
    """The value of a module-level assignment to ``name``, as data.

    `ast.literal_eval` rather than an import: this suite must not load Django,
    and the module under inspection is a Django test module that walks the app
    registry at import time. It also means the constant has to STAY a literal —
    a value computed at runtime cannot be read here, and the test says so
    rather than silently skipping it.
    """
    for statement in _parsed(source).body:
        targets = (statement.targets if isinstance(statement, ast.Assign)
                   else [statement.target] if isinstance(statement, ast.AnnAssign)
                   else [])
        for target in targets:
            if isinstance(target, ast.Name) and target.id == name:
                try:
                    return ast.literal_eval(statement.value)
                except ValueError as problem:
                    raise AssertionError(
                        f"`{name}` in {GATE_MODULE} is no longer a plain "
                        f"literal, so it cannot be held to the ledger without "
                        f"importing Django into this suite: {problem}"
                    ) from problem
    raise AssertionError(f"{GATE_MODULE} declares no `{name}`")


def excused(source, constant):
    """`{gate: {site: (id, found)}}` as the gate module declares it.

    Normalised so both constants have one shape: the ledger's entries carry a
    recorded `found`, the permanent exceptions do not — the schema gives them no
    such field, because no rename is coming and there is nothing to compare a
    future value against.
    """
    declared = literal_constant(source, constant)
    return {
        gate: {site: tuple(entry) if isinstance(entry, tuple) else (entry, None)
               for site, entry in sites.items()}
        for gate, sites in declared.items()
    }


def recorded(records, gate):
    """The same shape, from the loaded ledger or exception list."""
    return {record.site: (record.id, getattr(record, "found", None))
            for record in records if record.gate == gate}


def disagreements(excused_sites, recorded_sites):
    """Every way two sides of one gate fail to say the same thing.

    A real predicate rather than an inline `==`, so the negative controls below
    can push synthetic pairs through the function the assertions actually use.
    An `assert a != b` control proves that two dicts differ, which was never in
    doubt.
    """
    faults = []
    for site in sorted(set(excused_sites) - set(recorded_sites)):
        faults.append(f"{site} is excused by the gate but is in no record — a "
                      f"suppression with no debt behind it")
    for site in sorted(set(recorded_sites) - set(excused_sites)):
        faults.append(f"{site} is recorded in gates/ but the gate excuses "
                      f"nothing there — the entry is unreachable")
    for site in sorted(set(excused_sites) & set(recorded_sites)):
        if excused_sites[site] != recorded_sites[site]:
            faults.append(f"{site}: the gate says {excused_sites[site]}, "
                          f"gates/ says {recorded_sites[site]}")
    return faults


@pytest.fixture(scope="module")
def gate_source():
    return (REPO_ROOT / GATE_MODULE).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def programme():
    return load_programme(GATES_DIR, REPO_ROOT)


# ---------------------------------------------------------------------------
# The agreement
# ---------------------------------------------------------------------------

def test_the_gate_module_exists_and_declares_both_allowlists(gate_source):
    """Vacuity guard. Every assertion below reads these two constants, and a
    renamed module or constant would otherwise turn this file green by making
    all of its comparisons empty."""
    ledgered = excused(gate_source, LEDGER_CONSTANT)
    excepted = excused(gate_source, EXCEPTIONS_CONSTANT)

    assert set(ledgered) <= set(MODEL_NAMING_GATES), (
        f"{LEDGER_CONSTANT} covers {sorted(ledgered)}, which is not a subset "
        f"of the gates this module installs")
    assert sum(len(sites) for sites in ledgered.values()) > 0
    assert excepted.get("G9"), "the ConnectOAuthState exception is not excused"


def test_every_excused_site_is_a_recorded_debt(gate_source, programme):
    """A site the gate excuses must be a debt somebody owes, and the same debt.

    This is the direction that matters most. An excused site with no ledger
    entry is a suppression the ratchet cannot see, owed by no slice and cleared
    by nobody — #155 §17's failure, hiding inside the mechanism built to close
    it.

    Driven off the union of both sides, so a gate that gains its first entry
    later is compared on the day it does rather than when somebody remembers to
    add it here.
    """
    declared = excused(gate_source, LEDGER_CONSTANT)
    for gate in sorted(set(MODEL_NAMING_GATES) | set(declared)
                       | {entry.gate for entry in programme.entries}):
        faults = disagreements(declared.get(gate, {}),
                               recorded(programme.entries, gate))
        assert not faults, (
            f"{gate}: {GATE_MODULE} and gates/migration-ledger.yaml "
            f"disagree.\n  " + "\n  ".join(faults))


def test_every_permanent_exception_is_excused_and_stated(gate_source, programme):
    declared = excused(gate_source, EXCEPTIONS_CONSTANT)
    for gate in sorted(set(MODEL_NAMING_GATES) | set(declared)
                       | {exception.gate for exception in programme.exceptions}):
        faults = disagreements(declared.get(gate, {}),
                               recorded(programme.exceptions, gate))
        assert not faults, (
            f"{gate}: {GATE_MODULE} and gates/permanent-exceptions.yaml "
            f"disagree.\n  " + "\n  ".join(faults))


def test_a_debt_and_an_exception_are_never_the_same_site(gate_source):
    """The two lists mean different things, so a site may not be in both.

    A site recorded as both a debt and a permanent exception would be owed by a
    slice and simultaneously declared as never being fixed — and the ledger
    would never reach the zero G22 depends on.
    """
    ledgered = excused(gate_source, LEDGER_CONSTANT)
    excepted = excused(gate_source, EXCEPTIONS_CONSTANT)
    for gate in set(ledgered) & set(excepted):
        both = set(ledgered[gate]) & set(excepted[gate])
        assert not both, f"{gate}: recorded as both a debt and an exception: {both}"


def test_every_excused_site_names_a_file_in_the_platform_tree(gate_source):
    """A site is `<repository-relative path>::<Model>[.field]`, and the path
    exists. An unresolvable site excuses nothing while looking like it does, and
    the ledger entry that shares it would be unfalsifiable."""
    sites = [
        site
        for source in (excused(gate_source, LEDGER_CONSTANT),
                       excused(gate_source, EXCEPTIONS_CONSTANT))
        for sites in source.values()
        for site in sites
    ]
    assert sites, "no sites to check — the guard above should have caught this"
    for site in sites:
        assert site.count("::") == 1, f"`{site}` is not a `path::Model` site"
        path, _ = site.split("::")
        assert path.startswith("ubb-platform/"), (
            f"`{site}` is not in the platform tree")
        assert (REPO_ROOT / path).is_file(), f"`{path}` does not exist"


# ---------------------------------------------------------------------------
# Negative controls — the reader flags a disagreement it is shown.
#
# Without these the comparisons above could be structurally incapable of
# failing, which is the defect this whole directory exists to prevent.
# ---------------------------------------------------------------------------

SYNTHETIC = '''\
LEDGERED_VIOLATIONS = {
    "G9": {"ubb-platform/apps/x/models.py::Alpha": ("g9-alpha", "ubb_beta")},
}

PERMANENT_EXCEPTIONS = {}

COMPUTED = "a" + "b"
'''

SITE = "ubb-platform/apps/x/models.py::Alpha"


def _synthetic_allowlist():
    return excused(SYNTHETIC, LEDGER_CONSTANT)["G9"]


def test_negative_control_an_unrecorded_suppression_is_flagged():
    """The failure this file exists for: the gate excuses a site that no ledger
    entry covers. Pushed through `disagreements`, the function the assertions
    above call — not an inequality between two dicts."""
    faults = disagreements(_synthetic_allowlist(), {})
    assert len(faults) == 1
    assert "suppression with no debt behind it" in faults[0]


def test_negative_control_an_unreachable_ledger_entry_is_flagged():
    """The other direction: a debt recorded against a site the gate does not
    excuse. Nothing would ever clear it, because nothing was ever suppressed."""
    faults = disagreements({}, _synthetic_allowlist())
    assert len(faults) == 1
    assert "the entry is unreachable" in faults[0]


def test_negative_control_a_relabelled_entry_is_flagged():
    """Identity includes the id: relabelling one side alone is a disagreement,
    because a reader following an id from the gate to the ledger would find
    nothing."""
    allowlist = _synthetic_allowlist()
    faults = disagreements(allowlist, {SITE: ("g9-renamed", "ubb_beta")})
    assert len(faults) == 1 and "g9-renamed" in faults[0]


def test_negative_control_a_drifted_found_value_is_flagged():
    """The same site and the same id, recording a different observed value. The
    site alone is too coarse an identity — see the platform suite's
    `test_every_seeded_table_entry_still_names_the_table_it_recorded`."""
    allowlist = _synthetic_allowlist()
    faults = disagreements(allowlist, {SITE: ("g9-alpha", "ubb_gamma")})
    assert len(faults) == 1 and "ubb_gamma" in faults[0]


def test_positive_control_two_sides_that_agree_produce_no_faults():
    allowlist = _synthetic_allowlist()
    assert disagreements(allowlist, dict(allowlist)) == []


def test_negative_control_a_computed_constant_is_refused():
    """A constant that stops being a literal must fail loudly, not vanish.

    `"a" + "b"` is the smallest expression `literal_eval` refuses. If this
    raised nothing, a future edit that built the allowlist from a loop would
    turn every comparison above into a silent skip.
    """
    with pytest.raises(AssertionError, match="no longer a plain literal"):
        literal_constant(SYNTHETIC, "COMPUTED")


def test_negative_control_an_absent_constant_is_refused():
    with pytest.raises(AssertionError, match="declares no `NOT_THERE`"):
        literal_constant(SYNTHETIC, "NOT_THERE")
