"""The console words every axis the server reserves, and reserves no other.

⚠ **THIS LIVES HERE BECAUSE IT IS AN AGREEMENT BETWEEN TWO TREES, AND A CHECK
HOSTED BY ONE PARTY TO AN AGREEMENT CAN ONLY EVER SEE ITS OWN SIDE**
(`docs/conventions/testing.md`). #506 gave `apps/ui/src/lib/grouping-axis.ts`
five authored words for the axes every tenant has, and its first draft claimed a
vitest case pinned them "against the server's ``RESERVED_KEYS``". It did not and
could not: the console cannot read Python, so that test compared the map against
five literals typed into the same file, and a sixth reserved word on the server
would have been invisible to it. `/code-review` found the claim on both axes.

This suite is the one place that can hold both sides at once — it is Node-free
and Django-free by construction, so it reads each tree as TEXT rather than by
importing either. The Python side is parsed with :mod:`ast`, which is exact; the
TypeScript side with a regex, which is how `test_label_catalogue.py` has read
that tree since #210.

**Why the agreement matters.** `grouping_options` sends UBB's own axes with an
EMPTY ``label`` — the contract states that as a rule rather than a gap, because
the tenant's word is the tenant's and UBB's is the surface's to supply. So an
axis the server reserves and the console has no word for does not fail: it
renders as a marked token, which is right for a value nobody has words for and
wrong for one of the five words UBB chose. And a word here for an axis the
server never offers is dead copy nothing can reach.
"""

import ast
import re

import pytest

from _helpers import REPO_ROOT

#: The server's reserved grouping axes — the words every tenant has whatever it
#: declares, which a tenant may therefore never declare for itself.
RESERVED_KEYS_MODULE = "ubb-platform/apps/platform/grouping_fields/models.py"
RESERVED_KEYS_NAME = "RESERVED_KEYS"

#: The console's words for those same axes.
CONSOLE_TITLES_MODULE = "apps/ui/src/lib/grouping-axis.ts"
CONSOLE_TITLES_NAME = "UBB_AXIS_TITLES"

#: One `key: "Words",` line of the console's object literal. Deliberately not a
#: TypeScript parse: the object is a flat map of identifier to string, this
#: suite ships no TS parser, and the vacuity guard below is what stops a regex
#: that silently matches nothing from passing.
_TITLE_ENTRY = re.compile(r"^\s*(\w+)\s*:\s*\"[^\"]+\",\s*$", re.MULTILINE)


def _reserved_keys() -> set[str]:
    """The server's set, read off the assignment with :mod:`ast`."""
    source = (REPO_ROOT / RESERVED_KEYS_MODULE).read_text(encoding="utf-8")
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Assign):
            continue
        if not any(isinstance(target, ast.Name)
                   and target.id == RESERVED_KEYS_NAME
                   for target in node.targets):
            continue
        assert isinstance(node.value, (ast.Tuple, ast.List)), (
            f"{RESERVED_KEYS_NAME} is no longer a literal sequence, so this "
            f"cannot read it without running Django — which this suite may not "
            f"do. Read it however it is spelled now, or say here why it cannot "
            f"be read; do not leave the agreement unchecked.")
        return {element.value for element in node.value.elts
                if isinstance(element, ast.Constant)}
    raise AssertionError(
        f"{RESERVED_KEYS_MODULE} no longer assigns {RESERVED_KEYS_NAME}. It is "
        f"the server's list of axes every tenant has; if it moved, this "
        f"agreement has to follow it rather than quietly stop checking.")


def _console_titles() -> set[str]:
    """The console's set, read off the object literal's own keys."""
    source = (REPO_ROOT / CONSOLE_TITLES_MODULE).read_text(encoding="utf-8")
    start = source.find(f"{CONSOLE_TITLES_NAME} = {{")
    assert start != -1, (
        f"{CONSOLE_TITLES_MODULE} no longer declares {CONSOLE_TITLES_NAME}")
    end = source.index("};", start)
    return {match.group(1)
            for match in _TITLE_ENTRY.finditer(source[start:end])}


@pytest.fixture(scope="module")
def reserved():
    return _reserved_keys()


@pytest.fixture(scope="module")
def titled():
    return _console_titles()


def test_both_sides_were_actually_read(reserved, titled):
    """The vacuity floor, and it is not decoration.

    Two readers of two trees by text, one of them a regex: the failure mode that
    matters is that a rename makes one side read as the empty set and every
    agreement below passes by agreeing about nothing. Both readers raise on a
    missing declaration; this pins that neither returned an empty answer.
    """
    assert reserved, f"read no reserved axis out of {RESERVED_KEYS_MODULE}"
    assert titled, f"read no axis word out of {CONSOLE_TITLES_MODULE}"


def test_the_console_words_every_axis_the_server_reserves(reserved, titled):
    """The direction that costs a tenant something.

    An axis the server offers and the console has no word for renders as a
    marked token. That is the right answer for a value nobody has words for, and
    the wrong one for `customer` — so this is the half that would let a sixth
    reserved word ship looking like a foreign token.
    """
    assert reserved <= titled, (
        f"the server reserves {sorted(reserved - titled)} and "
        f"{CONSOLE_TITLES_MODULE} has no word for it. The discovery contract "
        f"sends UBB's own axes with an empty `label` precisely because the "
        f"wording is the surface's to supply, so an axis with none renders as "
        f"a raw token beside words UBB authored.")


def test_the_console_words_no_axis_the_server_does_not_reserve(reserved, titled):
    """The other direction, which costs nobody anything and is still a defect.

    A word for an axis the server never offers is copy no render can reach, and
    the reason to catch it is that it reads as coverage. It is also what would
    be left behind if a reserved word were ever retired.
    """
    assert titled <= reserved, (
        f"{CONSOLE_TITLES_MODULE} words {sorted(titled - reserved)}, which "
        f"{RESERVED_KEYS_MODULE} does not reserve. Nothing can render it: the "
        f"discovery contract only ever sends the server's own axes with an "
        f"empty label.")
