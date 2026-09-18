"""A rule selects on what it always did, and nothing a rule IS becomes an axis.

⚠ **THE DECLARED GROUPING SCHEMA DOES DOUBLE DUTY** (map #137; slice 7 §21):
it is the vocabulary a report groups by AND the vocabulary a rule selects on.
#509 made the console's pricing feature take its selector words from the
grouping vocabulary — `selectorTitle` in
`apps/ui/src/features/pricing/lib/rules.ts`, over `ubbAxisTitle` — which is the
right sharing, and also the easiest place for either role to leak into the
other:

* a reporting axis readmitted to rate selection, which #145 §5 forbade, or a
  rollup, which #147 §2 took out of pricing by name; and
* a pricing concept made groupable in analytics. The two vocabularies share a
  schema; they do not share a role.

Both are agreements between trees, so they are checked here rather than from
either side (`docs/conventions/testing.md`): the console cannot read Python and
the server cannot read the console. This suite reads the code without importing
it — the Python with :mod:`ast`, the TypeScript with a regex, the published
contract as JSON — the shape `test_grouping_axis_vocabulary.py` uses next door,
and the vocabulary registry through `load_registry`, the loader CI itself runs.

The server's own half of the first prohibition is pinned where the server can
see it, in `apps/metering/pricing/tests/test_rate_selectors.py` and
`apps/metering/tests/test_the_grouping_contract.py`. What only this suite can
see is whether the CONSOLE still offers exactly what the server selects on.
"""

import ast
import json
import re

import pytest

from _helpers import REPO_ROOT, module_literal
from tools.vocabulary import load_registry

#: Where the server says what a rule selects on.
RATE_MODULE = "ubb-platform/apps/metering/pricing/models.py"

#: Where the console says which named selectors a rule offers.
CONSOLE_SELECTORS_MODULE = "apps/ui/src/features/pricing/lib/rules.ts"
CONSOLE_SELECTORS_NAME = "NAMED_SELECTORS"

#: The axes every tenant may group by whatever it declares.
RESERVED_KEYS_MODULE = "ubb-platform/apps/platform/grouping_fields/models.py"

#: The published bodies a rule is read and written through: a book's rule, a
#: change to one, and one customer's own deal.
RULE_SCHEMAS = ("RateOut", "BookChangeIn", "CustomerOverrideIn")

#: The tenant's declared fields ride on a rule as ten slot columns on the read
#: side and as one map keyed by the declared key on the write side. They are
#: the vocabulary's shared half — a selector and an axis both, by design
#: (ADR-0005) — so they leave "what a rule is" by this prefix rather than by a
#: list that would have to be kept in line with the slot count.
DECLARED_FIELD_PREFIX = "grouping_field"

#: One quoted identifier in the console's array literal. A regex rather than a
#: TypeScript parse, for the reason the module next door gives; the vacuity
#: floor below is what stops it silently matching nothing.
_LIST_ITEM = re.compile(r"\"(\w+)\"")


def _server_named_selectors() -> tuple[str, ...]:
    """The spelled half of `Rate.SELECTORS`, read with :mod:`ast`.

    The tuple is the named selectors written out, followed by the slot half
    unpacked from the grouping registry. Only the written half is a claim about
    names, and it is the half the console offers by name.
    """
    tree = ast.parse((REPO_ROOT / RATE_MODULE).read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if not (isinstance(node, ast.ClassDef) and node.name == "Rate"):
            continue
        for statement in node.body:
            if not (isinstance(statement, ast.Assign) and any(
                    isinstance(target, ast.Name) and target.id == "SELECTORS"
                    for target in statement.targets)):
                continue
            assert isinstance(statement.value, ast.Tuple), (
                f"`Rate.SELECTORS` in {RATE_MODULE} is no longer a tuple "
                f"display, so this cannot read its named half without running "
                f"Django. Read it however it is spelled now; do not leave the "
                f"agreement unchecked.")
            return tuple(element.value for element in statement.value.elts
                         if isinstance(element, ast.Constant))
    raise AssertionError(
        f"{RATE_MODULE} no longer declares `Rate.SELECTORS`. It is the "
        f"server's statement of what a rule may pin; if it moved, this "
        f"agreement has to follow it rather than quietly stop checking.")


def _console_named_selectors() -> tuple[str, ...]:
    """The console's list, read off the array literal it is declared as."""
    source = (REPO_ROOT / CONSOLE_SELECTORS_MODULE).read_text(encoding="utf-8")
    start = source.find(f"export const {CONSOLE_SELECTORS_NAME} = [")
    assert start != -1, (
        f"{CONSOLE_SELECTORS_MODULE} no longer declares {CONSOLE_SELECTORS_NAME} "
        f"as an array literal")
    end = source.index("]", start)
    return tuple(_LIST_ITEM.findall(source[start:end]))


@pytest.fixture(scope="module")
def server_selectors():
    return _server_named_selectors()


@pytest.fixture(scope="module")
def console_selectors():
    return _console_named_selectors()


@pytest.fixture(scope="module")
def axes():
    """Every axis a report may group by that is UBB's rather than a tenant's."""
    rollups = load_registry(REPO_ROOT / "domain-vocabulary").concepts[
        "analytics_rollup"].values
    return set(module_literal(RESERVED_KEYS_MODULE, "RESERVED_KEYS")) | set(rollups)


@pytest.fixture(scope="module")
def rule_terms(server_selectors):
    """What a rule carries that is not something it selects on."""
    document = json.loads(
        (REPO_ROOT / "openapi" / "v1.json").read_text(encoding="utf-8"))
    schemas = document["components"]["schemas"]
    carried = set().union(*(schemas[name]["properties"] for name in RULE_SCHEMAS))
    return {name for name in carried
            if name not in server_selectors
            and not name.startswith(DECLARED_FIELD_PREFIX)}


def test_every_reader_read_something(server_selectors, console_selectors, axes,
                                     rule_terms):
    """The vacuity floor, and it is not decoration.

    Five reads over four sources — the platform's Python, the console, the
    registry and the published contract — one of them a regex and one a
    subtraction: the failure that matters is a rename that leaves one side
    reading as the empty set, after which every agreement below passes by
    agreeing about nothing. The pricing half is floored by NAME rather than by size, because a
    subtraction that took everything would still leave something behind for a
    size check to count.
    """
    assert server_selectors, f"read no named selector out of {RATE_MODULE}"
    assert console_selectors, (
        f"read no named selector out of {CONSOLE_SELECTORS_MODULE}")
    assert axes, "read no reserved axis and no rollup"
    assert {"measurement_key", "pricing_method"} <= rule_terms, (
        f"what a rule carries beyond its selectors no longer includes the "
        f"quantity it prices and how it derives the price — the subtraction "
        f"has taken the part of a rule this suite exists to keep out of the "
        f"axes. Read: {sorted(rule_terms)}")


def test_the_console_offers_every_named_selector_the_server_selects_on(
        server_selectors, console_selectors):
    """The direction that costs a tenant something.

    A selector the server resolves on and the console does not offer is a rule
    a tenant can have and cannot write: declaring one means stating its value,
    and there would be nowhere to state it.
    """
    missing = set(server_selectors) - set(console_selectors)
    assert not missing, (
        f"the server selects a rule on {sorted(missing)} and "
        f"{CONSOLE_SELECTORS_MODULE} offers no input for it, so a rule pinned "
        f"on it can exist and cannot be declared from the console.")


def test_the_console_offers_no_named_selector_the_server_does_not_select_on(
        server_selectors, console_selectors):
    """The reporting door, from the console's side (#145 §5, #147 §2).

    The console's list is typed against the grouping vocabulary, and that
    vocabulary has a fifth axis — the customer — which is a reporting axis and
    not a selector. So the list's own type does not keep it out. A selector
    input the server has no column for is worse than a refusal: an undeclared
    body key is dropped rather than refused, so the rule a tenant declares
    would pin less than the form showed them it pinned.
    """
    extra = set(console_selectors) - set(server_selectors)
    assert not extra, (
        f"{CONSOLE_SELECTORS_MODULE} offers {sorted(extra)} as a rate selector "
        f"and `Rate.SELECTORS` does not select on it. A grouping axis that is "
        f"not a selector has been readmitted to pricing through the vocabulary "
        f"the two share.")


def test_nothing_a_rule_carries_but_its_selectors_is_an_axis(axes, rule_terms):
    """The other direction: no pricing concept becomes groupable (#509).

    What a rule APPLIES TO is shared with the grouping vocabulary by design.
    What a rule IS — the quantity it prices, how it derives the price, what it
    charges, which book holds it and when it holds — is pricing's alone, and an
    axis spelled like one of those would make a pricing concept something a
    report groups by. The console cannot add such an axis on its own account:
    `test_grouping_axis_vocabulary.py` holds its words for UBB's axes equal to
    the server's reserved set, which is the set read here.
    """
    shared = rule_terms & axes
    assert not shared, (
        f"{sorted(shared)} is carried by a rule as one of its own terms and is "
        f"also an axis a report groups by. A rule's terms are pricing's; only "
        f"what a rule selects on is shared with the grouping vocabulary.")
