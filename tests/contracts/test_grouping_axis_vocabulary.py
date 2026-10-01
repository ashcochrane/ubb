"""The axes UBB reserves are declared once, and both trees hold that declaration.

⚠ **THIS MODULE USED TO HOLD TWO HAND-KEPT LISTS EQUAL, AND NOW HOLDS NEITHER
TREE TO KEEPING ONE** (#544, landed by #575). The server reserved five words in
a tuple typed beside the model; the console worded the same five in an object
literal typed beside the picker; and this suite read both as text and pinned the
two sets equal, because a check hosted by one party to an agreement can only
ever see its own side (`docs/conventions/testing.md`). Nothing generated either
list. That was the residual #506 recorded as "nobody owns the question yet".

The owner ruled the five canonical, and the registry now declares them as
`reserved_grouping_axis`. So the agreement is no longer two lists that happen to
match: it is one declaration with two consumers that hold it BY REFERENCE, and
what this module pins is the three things that make that true and keep it true.

1. **The registry declares exactly the five.** Spelled out below on purpose — a
   test is the one place a copy belongs, because it is what makes a sixth axis
   come past a person rather than arrive by an edit to a YAML file alone.
2. **The server's reserved words ARE the generated set**, with nothing typed
   beside it. The census proves the module imports the set; it cannot prove the
   tuple is built from the import and from nothing else, which is the half a
   literal `+ ("sixth",)` would slip through.
3. **The console words the axes through the generated label keys**, and types
   no title for one of them itself. The census proves the import here too; what
   it cannot see is an object literal worded beside it.

Read without importing either tree — the Python with :mod:`ast`, which is exact,
and the TypeScript with a regex, which is how `test_label_catalogue.py` has read
that tree since #210 — because this suite is Node-free and Django-free by
construction. The NAMES it looks for are asked of the generator rather than
typed, for the reason the census gives: a target is the authority on what it
binds.

**The SDK is the third consumer and has no test here, deliberately.** No
hand-written SDK module names an axis, so there is no list for it to keep and
nothing for a reader to find. It consumes the concept as the constants generated
into `ubb/vocabulary.py`, which ride the zero-diff regeneration gate; the one
assertion below is that they are there.
"""

import ast
import json
import re

import pytest

from _helpers import REPO_ROOT
from tools.consumers import take_census
from tools.vocabulary import load_registry
from tools.vocabulary.generate import (
    BACKEND_CONSTANTS,
    CONSOLE_VOCABULARY,
    SDK_CONSTANTS,
)

CONCEPT = "reserved_grouping_axis"

#: The axes every tenant has whatever it declares. THE ONE COPY, and it is here
#: so that changing the set is a diff in two files a reviewer reads rather than
#: in one.
THE_RESERVED_AXES = ("customer", "provider", "event_type", "task_type",
                     "subtask_type")

#: Where the server says which words a tenant may not declare.
SERVER_MODULE = "ubb-platform/apps/platform/grouping_fields/models.py"
SERVER_NAME = "RESERVED_KEYS"

#: Where the console turns one of those axes into words.
CONSOLE_MODULE = "apps/ui/src/lib/grouping-axis.ts"

#: The catalogue the wording lives in.
CATALOGUE = "apps/ui/src/locales/en.json"


@pytest.fixture(scope="module")
def registry():
    return load_registry(REPO_ROOT / "domain-vocabulary", REPO_ROOT)


@pytest.fixture(scope="module")
def concept(registry):
    return registry.concepts[CONCEPT]


@pytest.fixture(scope="module")
def census(registry):
    return take_census(REPO_ROOT, registry)


def _read(path):
    return (REPO_ROOT / path).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# The two readers. Pure functions of SOURCE TEXT, so the controls at the bottom
# can hand them a tree with a sixth name in it without touching the real one.
# ---------------------------------------------------------------------------

def typed_beside_the_generated_set(source, set_name):
    """What the server's reserved words are built from besides ``set_name``.

    Returns ``(names_the_generated_set, literals)``: whether the assignment
    reads the generated set at all, and every string it spells for itself. A
    reserved list held by reference answers ``(True, [])``. Anything else is a
    list somebody keeps.
    """
    for node in ast.parse(source).body:
        if not (isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == SERVER_NAME
                for target in node.targets)):
            continue
        names = {inner.id for inner in ast.walk(node.value)
                 if isinstance(inner, ast.Name)}
        literals = sorted(inner.value for inner in ast.walk(node.value)
                          if isinstance(inner, ast.Constant)
                          and isinstance(inner.value, str))
        return set_name in names, literals
    raise AssertionError(
        f"{SERVER_MODULE} no longer assigns {SERVER_NAME}. It is the server's "
        f"list of axes every tenant has; if it moved, this module has to "
        f"follow it rather than quietly stop checking.")


#: One `key: "Words"` entry of an object literal — a name beside the string it
#: is to be shown as — whether it has a line to itself or shares one. ANY key,
#: deliberately: a reader keyed on the five declared axes would see a title
#: retyped for one of them and miss the case this module is named for, a SIXTH
#: word the registry never declared.
_KEYED_STRING = re.compile(
    r"(?:^|[{,])\s*[\"']?(\w+)[\"']?\s*:\s*[\"'`]", re.MULTILINE)

#: The one keyed string the console's axis module legitimately holds: the
#: discriminant of the answer it returns (`{ kind: "worded", … }`). Named
#: rather than matched around, so a second exemption is a line a reviewer reads.
NOT_A_TITLE = frozenset({"kind"})


def titles_typed_in_the_console(source):
    """Every name the console module words for itself, in an object literal.

    The shape the hand-kept title map had, and the shape a sixth word would
    arrive in. The module's whole job is to turn an axis into words by LOOKUP,
    so it has no reason to hold a keyed string of any kind — which is what lets
    this be a statement about the module rather than about five spellings.
    Deliberately not a TypeScript parse: this suite ships no TS parser, and the
    control below is what stops a regex that silently matches nothing from
    passing.
    """
    return sorted(set(_KEYED_STRING.findall(source)) - NOT_A_TITLE)


# ---------------------------------------------------------------------------
# 1. The declaration
# ---------------------------------------------------------------------------

def test_the_registry_declares_exactly_the_five(concept):
    assert concept.kind == "closed"
    assert tuple(concept.values) == THE_RESERVED_AXES, (
        f"`{CONCEPT}` no longer declares the five axes this module names. If "
        f"an axis was added or retired on purpose, change the tuple here in "
        f"the same commit — and give `apps/metering/queries.py::"
        f"ALWAYS_PRESENT_AXES` the grain it resolves at, which its own "
        f"import-time assertion will otherwise refuse.")
    assert concept.label_key_prefix, (
        "a UBB-authored value with no label key has nowhere for its wording "
        "to hang (ADR-0008 §4)")


def test_both_consumers_are_declared_and_both_serve_it(concept, census):
    """The census's own verdict, asked of exactly this concept.

    G2 would accept a ledger entry in place of a served consumer. Nothing owes
    one here, and this is what keeps it that way: a consumer that stops
    importing the generated names is red in this module by name, rather than a
    debt somebody may record and leave.
    """
    declared = {(consumer.surface, consumer.path)
                for consumer in concept.consumers}
    assert declared == {("backend", SERVER_MODULE), ("console", CONSOLE_MODULE)}

    for surface in ("backend", "console"):
        assert census.serves(CONCEPT, surface), (
            f"the {surface} consumer of `{CONCEPT}` no longer holds every "
            f"value by reference: {census.extent(CONCEPT, surface)}")


# ---------------------------------------------------------------------------
# 2. The server
# ---------------------------------------------------------------------------

def test_the_servers_reserved_words_are_the_generated_set_and_nothing_else(
        concept):
    set_name = BACKEND_CONSTANTS.set_name(concept)
    reads_it, literals = typed_beside_the_generated_set(
        _read(SERVER_MODULE), set_name)

    assert reads_it, (
        f"{SERVER_NAME} in {SERVER_MODULE} is not built from `{set_name}`, so "
        f"the server is keeping its own list of the axes it reserves and a "
        f"sixth declared in the registry would not be reserved.")
    assert literals == [], (
        f"{SERVER_NAME} spells {literals} for itself beside the generated set. "
        f"A word reserved on the server and not declared in the registry is "
        f"one the console has no wording for and the SDK has no constant for.")


# ---------------------------------------------------------------------------
# 3. The console
# ---------------------------------------------------------------------------

def test_the_console_words_the_axes_through_the_generated_label_keys(concept):
    source = _read(CONSOLE_MODULE)
    label_keys = CONSOLE_VOCABULARY.label_keys_name(concept)

    assert re.search(rf"resolveLabel\(\s*{label_keys}\b", source), (
        f"{CONSOLE_MODULE} no longer resolves an axis through `{label_keys}`, "
        f"so whatever it renders for one of UBB's own axes is not the "
        f"catalogue's word for it.")
    assert titles_typed_in_the_console(source) == [], (
        f"{CONSOLE_MODULE} words {titles_typed_in_the_console(source)} for "
        f"itself, in an object literal. The wording for an axis UBB reserves "
        f"lives in {CATALOGUE}, keyed off the generated label keys, and an "
        f"axis the registry does not declare has no wording to give: a map "
        f"typed here is the hand-kept list #544 retired. If the entry is not "
        f"a title at all, move it out of the module that words axes.")


def test_the_catalogue_words_every_reserved_axis_and_no_other(concept):
    """Both directions, as the old cross-tree check held them.

    An axis the registry reserves with no word renders as a development error
    rather than as the word UBB chose; a word for an axis the registry does not
    reserve is copy no render can reach, and is what would be left behind if a
    reserved word were ever retired. G6 holds the whole catalogue to the whole
    registry; this names the one concept this module is about.
    """
    catalogue = json.loads(_read(CATALOGUE))
    prefix = f"{concept.label_key_prefix}."
    worded = {key[len(prefix):] for key, text in catalogue.items()
              if key.startswith(prefix) and text.strip()}

    assert worded == set(concept.values), (
        f"missing wording: {sorted(set(concept.values) - worded)}; wording "
        f"for an axis nobody reserves: {sorted(worded - set(concept.values))}")


# ---------------------------------------------------------------------------
# The SDK
# ---------------------------------------------------------------------------

def test_the_sdk_can_name_every_reserved_axis(concept):
    source = _read(SDK_CONSTANTS.path)
    names = {target.id for node in ast.parse(source).body
             if isinstance(node, ast.Assign) for target in node.targets
             if isinstance(target, ast.Name)}

    expected = set(SDK_CONSTANTS.handles(concept))
    assert len(expected) == len(concept.values) + 1, (
        "the SDK target should bind one constant per axis and one for the set")
    assert expected <= names, (
        f"{SDK_CONSTANTS.path} does not bind {sorted(expected - names)}, so "
        f"generated integration code has no name for that axis.")


# ---------------------------------------------------------------------------
# The controls: a sixth name in either consumer goes red
# ---------------------------------------------------------------------------

def test_control_a_sixth_word_typed_on_the_server_is_seen(concept):
    """The reader finds what it exists to find, in each shape it could arrive.

    Every assertion above about the server is an ABSENCE — no literal beside
    the set — and an absence is also what a reader pointed at the wrong node
    reports. So the same reader is fired at three trees that each carry the
    defect, and must name it.
    """
    set_name = BACKEND_CONSTANTS.set_name(concept)

    appended = f'{SERVER_NAME} = tuple(sorted({set_name})) + ("region",)\n'
    assert typed_beside_the_generated_set(appended, set_name) == (
        True, ["region"])

    unioned = f'{SERVER_NAME} = tuple(sorted({set_name} | {{"region"}}))\n'
    assert typed_beside_the_generated_set(unioned, set_name) == (
        True, ["region"])

    # The list as it stood before #575: five literals and no generated name.
    hand_kept = f"{SERVER_NAME} = {THE_RESERVED_AXES!r}\n"
    assert typed_beside_the_generated_set(hand_kept, set_name) == (
        False, sorted(THE_RESERVED_AXES))

    # And the shipped module is none of those.
    assert typed_beside_the_generated_set(
        _read(SERVER_MODULE), set_name) == (True, [])


def test_control_a_title_typed_in_the_console_is_seen(concept):
    """The same, for the console's reader.

    The map this module used to hold equal to the server's list, restored — and
    then a sixth word, which is the case the old cross-tree check existed for.
    """
    restored = (
        "export const UBB_AXIS_TITLES = {\n"
        '  customer: "Customer",\n'
        '  provider: "Provider",\n'
        '  event_type: "Event type",\n'
        '  task_type: "Kind of work",\n'
        '  subtask_type: "Kind of subtask",\n'
        "} as const;\n")
    assert titles_typed_in_the_console(restored) == sorted(THE_RESERVED_AXES)

    # THE SIXTH WORD — an axis the registry never declared, worded beside the
    # catalogue lookup — and a title retyped for one it did declare. Quoted and
    # template-string spellings both count.
    a_sixth = (
        "const EXTRA_TITLES = {\n"
        '  region: "Region",\n'
        "  'task_type': `Kind of work`,\n"
        "};\n")
    assert "region" not in concept.values
    assert titles_typed_in_the_console(a_sixth) == ["region", "task_type"]

    # A map squeezed onto one line is still a map.
    assert titles_typed_in_the_console(
        'const T = { customer: "Customer", region: "Region" };\n') == [
            "customer", "region"]

    # What is NOT a title: a union member, an argument, a typed field, and the
    # answer the module really returns — whose discriminant is the one keyed
    # string it may hold. Each line would be caught by a reader that matched a
    # quoted word anywhere, which is what makes this half able to fail.
    harmless = (
        'type Axis = "customer" | "provider";\n'
        'ubbAxisTitle("customer");\n'
        "  | { readonly kind: \"worded\"; readonly text: string }\n"
        '    ? { kind: "worded", text: ubbAxisTitle(name) }\n'
        '    : { kind: "unworded", text: name };\n')
    assert titles_typed_in_the_console(harmless) == []
    # And the exemption is one word wide: the same shape under another key is
    # a title again.
    assert titles_typed_in_the_console(
        '    ? { label: "Customer", text: name }\n') == ["label"]

    # And the shipped module is none of those.
    assert titles_typed_in_the_console(_read(CONSOLE_MODULE)) == []
