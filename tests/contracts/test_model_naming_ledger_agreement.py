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

import pytest

from _helpers import REPO_ROOT
from tools.gates import load_programme

GATES_DIR = REPO_ROOT / "gates"

GATE_MODULE = "ubb-platform/apps/platform/tests/test_model_naming.py"

#: The gates whose debts are recorded on both sides. G10 is deliberately absent:
#: it seeds nothing, so it has nothing to agree about — and a row here for a gate
#: with no entries would pass forever without asserting anything.
SEEDED_GATES = ("G9", "G11", "G12")

LEDGER_CONSTANT = "LEDGERED_VIOLATIONS"
EXCEPTIONS_CONSTANT = "PERMANENT_EXCEPTIONS"


def literal_constant(source, name):
    """The value of a module-level assignment to ``name``, as data.

    `ast.literal_eval` rather than an import: this suite must not load Django,
    and the module under inspection is a Django test module that walks the app
    registry at import time. It also means the constant has to STAY a literal —
    a value computed at runtime cannot be read here, and the test says so
    rather than silently skipping it.
    """
    tree = ast.parse(source)
    for statement in tree.body:
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


@pytest.fixture(scope="module")
def gate_source():
    return (REPO_ROOT / GATE_MODULE).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def programme():
    return load_programme(GATES_DIR, REPO_ROOT)


def _recorded(records, gate):
    """`{site: id}` for one gate, from the loaded ledger or exception list."""
    return {record.site: record.id for record in records if record.gate == gate}


# ---------------------------------------------------------------------------
# The agreement
# ---------------------------------------------------------------------------

def test_the_gate_module_exists_and_declares_both_allowlists(gate_source):
    """Vacuity guard. Every assertion below reads these two constants, and a
    renamed module or constant would otherwise turn this file green by making
    all of its comparisons empty."""
    ledgered = literal_constant(gate_source, LEDGER_CONSTANT)
    excepted = literal_constant(gate_source, EXCEPTIONS_CONSTANT)

    assert set(ledgered) == set(SEEDED_GATES), (
        f"{LEDGER_CONSTANT} covers {sorted(ledgered)}, not {list(SEEDED_GATES)}")
    assert sum(len(sites) for sites in ledgered.values()) > 0
    assert excepted.get("G9"), "the ConnectOAuthState exception is not excused"


def test_every_excused_site_is_a_recorded_debt(gate_source, programme):
    """A site the gate excuses must be a debt somebody owes.

    This is the direction that matters most. An excused site with no ledger
    entry is a suppression the ratchet cannot see, owed by no slice and cleared
    by nobody — #155 §17's failure, hiding inside the mechanism built to close
    it.
    """
    for gate in SEEDED_GATES:
        excused = literal_constant(gate_source, LEDGER_CONSTANT).get(gate, {})
        recorded = _recorded(programme.entries, gate)
        assert excused == recorded, (
            f"{gate}: the gate module and gates/migration-ledger.yaml "
            f"disagree.\n"
            f"  excused in {GATE_MODULE}: {sorted(excused.items())}\n"
            f"  recorded in the ledger:   {sorted(recorded.items())}")


def test_every_permanent_exception_is_excused_and_stated(gate_source, programme):
    for gate in sorted({exception.gate for exception in programme.exceptions}
                       | set(literal_constant(gate_source,
                                              EXCEPTIONS_CONSTANT))):
        excused = literal_constant(gate_source,
                                   EXCEPTIONS_CONSTANT).get(gate, {})
        recorded = _recorded(programme.exceptions, gate)
        assert excused == recorded, (
            f"{gate}: the gate module and gates/permanent-exceptions.yaml "
            f"disagree.\n"
            f"  excused in {GATE_MODULE}: {sorted(excused.items())}\n"
            f"  recorded in the exceptions: {sorted(recorded.items())}")


def test_a_debt_and_an_exception_are_never_the_same_site(gate_source):
    """The two lists mean different things, so a site may not be in both.

    A site recorded as both a debt and a permanent exception would be owed by a
    slice and simultaneously declared as never being fixed — and the ledger
    would never reach the zero G22 depends on.
    """
    ledgered = literal_constant(gate_source, LEDGER_CONSTANT)
    excepted = literal_constant(gate_source, EXCEPTIONS_CONSTANT)
    for gate in set(ledgered) & set(excepted):
        both = set(ledgered[gate]) & set(excepted[gate])
        assert not both, f"{gate}: recorded as both a debt and an exception: {both}"


def test_every_excused_site_names_a_file_in_the_platform_tree(gate_source):
    """A site is `<repository-relative path>::<Model>[.field]`, and the path
    exists. An unresolvable site excuses nothing while looking like it does, and
    the ledger entry that shares it would be unfalsifiable."""
    sites = [
        site
        for source in (literal_constant(gate_source, LEDGER_CONSTANT),
                       literal_constant(gate_source, EXCEPTIONS_CONSTANT))
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
    "G9": {"ubb-platform/apps/x/models.py::Alpha": "g9-alpha"},
}

PERMANENT_EXCEPTIONS = {}

COMPUTED = "a" + "b"
'''


def test_negative_control_a_missing_site_is_a_disagreement():
    excused = literal_constant(SYNTHETIC, LEDGER_CONSTANT)["G9"]
    assert excused != {}, "an empty ledger must not match a non-empty allowlist"


def test_negative_control_a_relabelled_entry_is_a_disagreement():
    """Identity includes the id: relabelling one side alone is a disagreement,
    because a reader following an id from the gate to the ledger would find
    nothing."""
    excused = literal_constant(SYNTHETIC, LEDGER_CONSTANT)["G9"]
    relabelled = {site: "g9-renamed" for site in excused}
    assert excused != relabelled


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
