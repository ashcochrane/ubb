"""No supplier-cost total is added up without saying what it left out (#327).

`Posting.provider_cost_micros` is nullable and `NULL` means *UBB has not
resolved this cost* (#317). SQL's aggregates skip `NULL`, so a bare
``Sum("provider_cost_micros")`` answers a number that looks complete and is not
— and answers it silently, which is the whole defect. Slice 3 replaced every one
of them with the pair `core.cost_totals` builds: the resolved sum AND the count
of postings excluded from it.

**A sweep is not a rule, and this file is the difference.** Fifteen call sites
were rewritten by hand across three modules; nothing stops the sixteenth being
written next week, in the shape that reads perfectly and reports a floor as a
figure. So the walker below fails on ANY `Sum` spelling that column outside the
one file that sums a column of that name which cannot be unknown.

**It asks the seam which column it is defending** rather than holding a copy of
the name. A gate that spells its own subject is a gate that goes quietly vacuous
the day the column is renamed — the failure this repository has now shipped
twice (#256 in the manifest, #285 in the ledger), and both times the surviving
control looked exactly like a passing one. The seam itself never appears in the
results: it takes the column as an argument, which is why the count below is
zero rather than one, and the vacuity guard is written against the walk having
happened rather than against a permitted site existing.

**The one exemption is DERIVED, not asserted.** `CustomerEconomics` — the
monthly margin snapshot — has a column of the same name that is `NOT NULL`, so
SQL's null-skipping cannot reach it and there is nothing for a count to report.
That is a claim about a model, so the exemption is granted by re-checking the
claim rather than by naming the file and hoping: the day that column becomes
nullable, the exemption goes red rather than silently covering a real defect.

⚠ **What this does NOT cover.** It reads the FIRST argument of a `Sum` call and
only when that argument is a literal string, so `Sum(F("provider_cost_micros"))`
or a column name assembled at runtime passes it. That is honest about being a
tripwire for the ordinary spelling rather than a proof about every aggregate,
and `api/v1/tests/test_a_cost_total_says_what_it_excluded.py` is where the
behaviour itself is asserted.
"""
import ast
from pathlib import Path

import pytest

from core.cost_totals import SUPPLIER_COST_COLUMN

# apps/platform/tests/test_no_bare_supplier_cost_aggregate.py -> ubb-platform/
PLATFORM_ROOT = Path(__file__).resolve().parents[3]

# Where a cost total can be built at all. Tests write the aggregates they are
# asserting about — including the Python reference loop the analytics pushdown
# is compared against — and a migration's aggregate runs once against the data
# as it stood, never as part of an answer to a tenant.
SEARCH_ROOTS = ("apps", "api", "core")
SKIP_PARTS = ("tests", "migrations")

#: The modules that sum a column of this name belonging to a DIFFERENT model,
#: each with the model it belongs to and how many such aggregates it holds.
#: Nothing here is taken on trust — `test_every_exemption_is_still_true` asks
#: each model whether its column can be unknown, and an exemption whose reason
#: has expired fails instead of covering for a defect.
#:
#: A count rather than a bare name, so a SECOND aggregate arriving in one of
#: these files is read by a person rather than inheriting somebody else's
#: exemption.
NON_POSTING_AGGREGATES = {
    "apps/subscriptions/queries.py": ("subscriptions", "CustomerEconomics", 1),
}


def _aggregate_sites(source: str, column: str) -> list[int]:
    """Line numbers of every ``Sum("<column>")`` call in one module."""
    lines = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", None)
        if name != "Sum" or not node.args:
            continue
        first = node.args[0]
        if isinstance(first, ast.Constant) and first.value == column:
            lines.append(node.lineno)
    return lines


def _walk():
    """(repo-relative path, aggregate line numbers) for every module searched."""
    for root in SEARCH_ROOTS:
        for path in sorted((PLATFORM_ROOT / root).rglob("*.py")):
            if any(part in SKIP_PARTS for part in path.parts):
                continue
            yield (path.relative_to(PLATFORM_ROOT).as_posix(),
                   _aggregate_sites(path.read_text(encoding="utf-8"),
                                    SUPPLIER_COST_COLUMN))


def test_the_supplier_cost_is_summed_only_where_it_cannot_be_unknown():
    found = {path: sites for path, sites in _walk() if sites}
    expected = {path: count for path, (_, _, count) in NON_POSTING_AGGREGATES.items()}
    assert {path: len(sites) for path, sites in found.items()} == expected, (
        f"A supplier-cost total must carry the count of postings it excluded. "
        f"Build it with core.cost_totals.cost_total_annotations() rather than a "
        f"bare Sum({SUPPLIER_COST_COLUMN!r}). Found: {found}"
    )


@pytest.mark.django_db
def test_every_exemption_is_still_true():
    """An exemption is a claim about a model, and this is where it is checked."""
    from django.apps import apps as django_apps

    for path, (app_label, model_name, _) in NON_POSTING_AGGREGATES.items():
        column = django_apps.get_model(app_label, model_name)._meta.get_field(
            SUPPLIER_COST_COLUMN)
        assert column.null is False, (
            f"{path} is exempt because {model_name}.{SUPPLIER_COST_COLUMN} "
            f"cannot be unknown. It can now — the aggregate there has to become "
            f"a pair, or the exemption has to say something else that is true.")


def test_the_walk_reached_the_modules_this_rule_is_about():
    """The vacuity guard.

    The rule above passes trivially if the walker never looks at anything — a
    bad glob, a moved root, a search path that stopped matching. Nothing proves
    the walk happened, because the answer it wants is an empty one: the seam
    takes the column as an argument and never spells it, so there is no
    permitted site to find. What is checked instead is that the three modules
    the sweep actually rewrote were read, and read as Python.
    """
    walked = {path for path, _ in _walk()}
    for module in ("apps/metering/queries.py", "api/v1/metering_endpoints.py",
                   "core/cost_totals.py"):
        assert module in walked, f"the walk never reached {module}"


def test_the_walker_would_see_one_that_was_reintroduced():
    """The positive control, taken against source text rather than the tree.

    Written as text because the tree is (correctly) clean: with no offender to
    point at, the only way to show the detector fires is to hand it one.
    """
    planted = f'total = qs.aggregate(cost=Sum("{SUPPLIER_COST_COLUMN}"))'
    assert _aggregate_sites(planted, SUPPLIER_COST_COLUMN) == [1]
    assert _aggregate_sites(
        f'models.Sum("{SUPPLIER_COST_COLUMN}")', SUPPLIER_COST_COLUMN) == [1]
    # A different column, and the ORM's other aggregates over this one, are not
    # this rule's business — a Count or an Avg is not a total a tenant reads as
    # money.
    assert _aggregate_sites('Sum("billed_cost_micros")', SUPPLIER_COST_COLUMN) == []
    assert _aggregate_sites(
        f'Avg("{SUPPLIER_COST_COLUMN}")', SUPPLIER_COST_COLUMN) == []
