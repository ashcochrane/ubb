"""A unit of work's ceiling is compared in ONE place (#452, slice 6 §3).

Three implementations of the comparison existed before this gate and two of
them disagreed: the live ingest lane stopped a unit strictly ABOVE its
ceiling, while the patrol's sweep, the analytics reached-count and the
registry's own decision rule said at-or-above. A unit landing exactly on its
ceiling survived the event that landed it and was killed by the patrol within
the hour, with no tipping event to attribute the stop to. The fix is one
predicate in `core/crossing.py`; this walker is what stops a fourth spelling
arriving next week, in either operator, in any module.

**What it refuses.** In production code, any ordering comparison — a Python
`Compare` in `<`, `<=`, `>` or `>=` whose operands name the ceiling column,
the total it races, or a local the enclosing function bound FROM either; or a
queryset lookup ending in `__lt`, `__lte`, `__gt` or `__gte` keyed on either
column or given the other through `F()`. Reading the function's own
assignments is what catches the shape the live lane's inline copy actually
had (`limit = unit.provider_cost_limit_micros; total > limit`), where the
comparison itself names only one column. Both column names are read off the
model rather than spelled here, so a rename reddens this file instead of
leaving it guarding nothing (the failure shape
`test_no_bare_supplier_cost_aggregate.py` names).

**The permitted sites are declared per module with a COUNT, never as a bare
set of paths.** A set only makes the easier half of the claim — that no OTHER
module compares — and a second compare arriving inside a permitted module
would leave it green (#349's lesson). Each permitted site is one a person has
read and found to be a different comparison from the crossing; at #452 there
are none, and the empty map is the claim.

**The predicate itself is invisible to this walk, deliberately.**
`core.crossing.ceiling_reached` compares two PARAMETERS and
`ceiling_reached_q` builds its lookup from two parameters, so neither names a
column and neither is counted here. What holds them to each other and to the
boundary is `core/tests/test_crossing.py` (the level and query forms pinned
over every boundary shape) and `TheRowAssessesItsOwnCeilingTest` in the work
app (the query form selecting exactly the rows the property calls reached).
The positive controls at the foot of this module are what show the walk can
see the three spellings it exists to refuse.
"""
import ast
from pathlib import Path

from apps.platform.work.models import Task

PLATFORM = Path(__file__).resolve().parents[3]

#: The two columns the compare is about, read off the model so the walker's
#: subject cannot go stale while the gate stays green.
THE_CEILING = Task._meta.get_field("provider_cost_limit_micros").attname
THE_KNOWN_TOTAL = Task._meta.get_field("total_provider_cost_micros").attname
COLUMNS = frozenset({THE_CEILING, THE_KNOWN_TOTAL})

#: Where an ordering compare against either column may still be spelled, and
#: how many times: `{module: count}`. Each would be a comparison a person has
#: read and found NOT to be the crossing. (The start gate's "a start may
#: request a ceiling lower than the declaration's, never higher" compares
#: the REQUEST against the declaration's default — a different column, so
#: it is not here and does not need to be.)
PERMITTED = {}

ORDERINGS = (ast.Lt, ast.LtE, ast.Gt, ast.GtE)
ORDERING_LOOKUPS = ("__lt", "__lte", "__gt", "__gte")
SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)


def production_modules():
    """Every production .py under apps/, api/ and core/ — no tests, no
    migrations, no scripts."""
    for top in ("apps", "api", "core"):
        for path in sorted((PLATFORM / top).rglob("*.py")):
            parts = path.relative_to(PLATFORM).parts
            if "tests" in parts or "migrations" in parts:
                continue
            yield path


def _names_in(node):
    """Every attribute, name and string literal spelled under ``node``."""
    out = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Attribute):
            out.add(sub.attr)
        elif isinstance(sub, ast.Name):
            out.add(sub.id)
        elif isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            out.add(sub.value)
    return out


def _lookup_names(call):
    """The keyword names of a call, plus the keys of any `**{...}` dict it
    unpacks — the two ways a queryset lookup is spelled."""
    names = set()
    for kw in call.keywords:
        if kw.arg is not None:
            names.add(kw.arg)
        elif isinstance(kw.value, ast.Dict):
            for key in kw.value.keys:
                if isinstance(key, ast.Constant) and isinstance(key.value, str):
                    names.add(key.value)
    return names


def _aliases_of(scope):
    """The locals a function binds FROM either column — `limit =
    unit.provider_cost_limit_micros` — so a compare against the alias is
    read as a compare against the column."""
    aliases = set()
    for node in ast.walk(scope):
        if isinstance(node, ast.Assign) and COLUMNS & _names_in(node.value):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    aliases.add(target.id)
    return aliases


def _ordering_lookup_on_a_column(call):
    """A queryset lookup keyed on either column, or comparing against it
    through `F()` — `total__gte=F("ceiling")` in either direction."""
    lookups = {n for n in _lookup_names(call) if n.endswith(ORDERING_LOOKUPS)}
    if not lookups:
        return False
    keyed = any(n.rsplit("__", 1)[0] in COLUMNS for n in lookups)
    return keyed or bool(COLUMNS & _names_in(call))


def compares_in(text):
    """The line of every ordering compare whose operands name either column
    or a local the enclosing function bound from one, and of every ordering
    lookup keyed on or compared against either column."""
    tree = ast.parse(text)
    found = []

    def walk(node, subjects):
        if isinstance(node, SCOPES):
            subjects = COLUMNS | _aliases_of(node)
        if isinstance(node, ast.Compare) and any(
                isinstance(op, ORDERINGS) for op in node.ops):
            if subjects & _names_in(node):
                found.append(node.lineno)
        elif isinstance(node, ast.Call) and _ordering_lookup_on_a_column(node):
            found.append(node.lineno)
        for child in ast.iter_child_nodes(node):
            walk(child, subjects)

    walk(tree, COLUMNS)
    return sorted(set(found))


def test_the_ceiling_is_compared_only_where_the_predicate_lives():
    walked = 0
    findings = {}
    for path in production_modules():
        walked += 1
        lines = compares_in(path.read_text(encoding="utf-8"))
        if lines:
            findings[path.relative_to(PLATFORM).as_posix()] = lines
    assert walked > 200, "the walk did not happen"  # 254 at #452
    counted = {module: len(lines) for module, lines in findings.items()}
    assert counted == PERMITTED, (
        "an ordering compare sits beside a unit's ceiling outside the one "
        "predicate — import `core.crossing.ceiling_reached` (a row in hand) "
        f"or `ceiling_reached_q` (a queryset) instead: {findings}")


def test_the_gate_reads_both_columns_off_the_model():
    """The vacuity guard on the subject: the model's own two column names,
    so a rename moves this file rather than leaving the walk searching for a
    spelling nothing has."""
    assert THE_CEILING == "provider_cost_limit_micros"
    assert THE_KNOWN_TOTAL == "total_provider_cost_micros"


# --- positive controls: the three spellings the walk exists to refuse ------

THE_LIVE_LANES_OLD_COMPARE = """
def _crossed_limit(unit):
    limit = unit.provider_cost_limit_micros
    return limit is not None and unit.total_provider_cost_micros > limit
"""

THE_PATROLS_OLD_FILTER = """
def sweep(tenant):
    return Task.objects.filter(
        tenant=tenant, status="active",
        provider_cost_limit_micros__isnull=False,
        total_provider_cost_micros__gte=F("provider_cost_limit_micros"))
"""

THE_REACHED_COUNTS_OLD_Q = """
def rollup(qs):
    return qs.annotate(limit_hit_count=Count("id", filter=Q(
        provider_cost_limit_micros__isnull=False,
        total_provider_cost_micros__gte=F("provider_cost_limit_micros"))))
"""

A_COMPARE_THAT_IS_NOT_ABOUT_THE_CEILING = """
def has_more(rows, limit):
    return len(rows) > limit
"""


def test_the_walk_sees_each_spelling_it_was_built_against():
    assert compares_in(THE_LIVE_LANES_OLD_COMPARE) == [4]
    assert compares_in(THE_PATROLS_OLD_FILTER) == [3]
    assert compares_in(THE_REACHED_COUNTS_OLD_Q) == [3]


def test_the_walk_ignores_a_compare_that_touches_neither_column():
    assert compares_in(A_COMPARE_THAT_IS_NOT_ABOUT_THE_CEILING) == []
