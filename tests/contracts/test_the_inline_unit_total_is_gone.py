"""The inline unit total died — the column and every named reader (#272).

Slice 2 retired the usage row's own nameless quantity. It is the one retirement
in the slice **the forbidden-term sweep can never prove**, and this module is
what stands in for it.

WHY THE SWEEP CANNOT DO IT. The plural word is registered as a retired *sense*
on `measurement_key`, not as a retired alias, because seventy-odd files carry
the bare token in four unrelated senses and one of them is ordinary English
inside three GENERATED modules whose text is rendered from concept summaries in
`domain-vocabulary/` — a permanent sweep exclusion. `retired_senses` is not
sweep input, so there is no "sweep finds zero" to reach and no ledger entry to
delete. The registry entry records that reasoning and its evidence; this module
records the half of the ruling the entry hands off: **the column and every
reader of it still die, and the deletion is proved by a targeted test.**

SO THIS GATE IS SENSE-SCOPED, NOT A WORD BAN, and both halves of that are put
under test below. It reads a NAMED list of readers rather than the tree, and it
matches the word only where it is shaped like a field — a declaration, a keyword
argument, a JSON key, a quoted key or an attribute read. Currency minor units,
rate arithmetic and ordinary English are all left alone, deliberately and
visibly: `test_the_control_the_surviving_sense_is_untouched` fires the same
matcher at a file that still carries the word field-shaped, in a sense slice 4
owns, and requires it to be found.

The strongest assertion here is not textual at all. The two published documents
are walked structurally for a schema property of that name, which is what
actually proves the field left the contract, the console's snapshot and every
client generated from either.
"""

import json
import re

import pytest

from _helpers import REAL_REGISTRY, REPO_ROOT
from tools.vocabulary import load_registry

#: The readers the ruling names, and what each one read. A path per entry, and a
#: sentence per path, because an absence list nobody can read is one that gets
#: extended by whoever is next inconvenienced by it.
READERS = {
    "ubb-platform/apps/metering/usage/models.py":
        "the column itself",
    "ubb-platform/apps/metering/queries.py":
        "metering's read contract — the summing aggregate, the null-to-zero "
        "coalescing that rendered it as a currency zero, and the summary field "
        "they fed",
    "ubb-platform/api/v1/schemas.py":
        "four public request/response schemas",
    "ubb-platform/api/v1/me_endpoints.py":
        "the customer-facing usage-summary endpoint, and the two schemas it "
        "answered with",
    "ubb-platform/api/v1/metering_endpoints.py":
        "the single/batch keyword map, and the detail serialiser",
    "ubb-platform/apps/metering/usage/services/usage_service.py":
        "the recording path that carried it from the door to the column",
    "ubb-sdk/ubb/client.py":
        "the SDK's hand-written recording call",
    "ubb-sdk/ubb/metering.py":
        "the SDK's metering client, which put it on the wire",
    "apps/ui/src/features/developers/api/mock.ts":
        "the console's mock recorder, which priced it",
    "apps/ui/src/features/developers/api/mock-data.ts":
        "the mock rate the line above multiplied it by",
    "apps/ui/src/features/developers/components/test-event-console.tsx":
        "the test-event form field",
    "apps/ui/src/features/developers/components/test-event-response.tsx":
        "the response stat beside it",
    "apps/ui/src/features/developers/lib/test-event.ts":
        "the form-values to request-body builder",
    "apps/ui/src/features/events/api/mock-data.ts":
        "the console's event fixtures",
    "apps/ui/src/features/events/api/mock.ts":
        "the mock detail lookup",
    "apps/ui/src/features/events/components/event-detail-page.tsx":
        "the detail page's stat row",
    "apps/ui/src/features/events/components/ledger-table.tsx":
        "the ledger column",
}

#: The two published documents, walked structurally rather than textually.
DOCUMENTS = ("openapi/v1.json", "apps/ui/src/api/schema.json")

#: The retired field's own names. The summary's grand total is the same field
#: one aggregate up and dies with it, so both are the subject here.
NAMES = ("units", "total_units")

#: The names as one alternation, built FROM `NAMES` rather than beside it — two
#: spellings of the same set drift, and the one that drifts is always the one
#: nobody is looking at (ADR-0006 §4, applied to a test's own constants).
_EITHER_NAME = "|".join(sorted((re.escape(name) for name in NAMES),
                               key=len, reverse=True))

#: The retired sense AS IT ACTUALLY APPEARED: a declaration, a keyword argument,
#: a JSON or object key, a quoted or backticked reference, or an attribute read.
#: Never the bare English word — three senses of it survive
#: (`measurement_key.retired_senses`), and a gate that condemned those would be
#: suppressed rather than obeyed.
#:
#: THE BACKTICK BRANCH IS DELIBERATE AND IT BINDS PROSE. A named reader may not
#: name this field even in a comment, which is why the note left on the model
#: describes the retirement without spelling it. That is the intended strictness:
#: these seventeen files are the ones that must have stopped referring to it, and
#: a doc comment saying `units` is how the console's mock rate survived a
#: previous pass. Every other file in the tree is free to say it.
FIELD = re.compile(
    rf"""(?<![0-9A-Za-z_])(?:{_EITHER_NAME})(?![0-9A-Za-z_])[ \t]*[:=](?!=)
      | \.(?:{_EITHER_NAME})(?![0-9A-Za-z_])
      | ["'`](?:{_EITHER_NAME})["'`]
    """, re.VERBOSE)

#: A file that still carries the word field-shaped, in a sense that survives:
#: the quantity a rate card was fed, recorded per measured key inside a pricing
#: receipt. That is rate arithmetic. It is NOT in READERS, and the control below
#: requires the matcher to find it there — which is what makes "sense-scoped" a
#: fact about this module rather than a claim in its docstring.
#:
#: ⚠ **SLICE 4 SCHEDULED THIS CONTROL TO GO RED AND IT DID NOT, AND THAT IS
#: WRITTEN DOWN HERE RATHER THAN LEFT AS A GREEN NOBODY EXPECTED.** The slice's
#: tripwire schedule (spec §29) predicted that the receipt's per-quantity key
#: would be renamed — which would EMPTY this control's subject, so the gate
#: would go vacuous as well as red, and #370 was named as the commit. It was
#: not: #366 ruled the key stays, and the argument is at
#: `pricing_service._component`. This word is a retired SENSE and not a retired
#: term — it is not sweep input, it holds no ledger seat, and no slice-4 ledger
#: entry counts it — so re-spelling it would be a change to the shape of a
#: STORED RECORD with no ticket behind it, and it would move the evidence block
#: in `retired.yaml` for a word this slice does not own. #370 checked the
#: prediction, found the subject intact, and left the control where it is.
#:
#: A prediction wrong about WHICH commit is not a check that was skipped. What
#: the ticket asked for and what is worth having either way is below: the
#: control is now shown to be carried by the word rather than passing for some
#: other reason, so the day a rename does empty this file the difference between
#: "red" and "red AND vacuous" is a test result instead of an argument.
SURVIVING_SENSE = ("ubb-platform/apps/metering/pricing/services/"
                   "pricing_service.py")

#: The singular. Slice 2's own canonical concept, and the reason the plural
#: could be retired as a sense at all — the sweep matches whole tokens, and `_`
#: is an identifier character.
SINGULAR = "unit"


def _read(relative):
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


def _schema_properties(node, path=""):
    """Every `properties` key in a JSON Schema document, by JSON pointer."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "properties" and isinstance(value, dict):
                for name in value:
                    yield f"{path}/properties/{name}"
            yield from _schema_properties(value, f"{path}/{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from _schema_properties(value, f"{path}/{index}")


@pytest.mark.parametrize("relative", sorted(READERS))
def test_no_named_reader_still_reads_the_inline_total(relative):
    """THE GATE, one reader at a time.

    Parametrized rather than accumulated so a survivor names itself in the test
    id: this list is long enough that a single failure listing seventeen paths
    would be read as "the gate is broken" rather than "this file is".
    """
    hits = [f"{number}: {line.strip()}"
            for number, line in enumerate(_read(relative).splitlines(), 1)
            if FIELD.search(line)]

    assert not hits, (
        f"`{relative}` still reads the retired inline total ({READERS[relative]}"
        f"). The column is gone, so this cannot be resolving against anything:\n"
        + "\n".join(f"  {hit}" for hit in hits))


@pytest.mark.parametrize("relative", DOCUMENTS)
def test_no_published_schema_still_carries_the_field(relative):
    """The structural half, and the one that actually binds.

    A property of this name in either document is a field a generated client
    still exposes — which is the whole failure mode, and the reason dropping it
    needed a reviewed break block of its own. Walked rather than grepped: the
    question is about the document's shape, and there is exactly one way to ask
    it that a reformatted file cannot answer differently.
    """
    document = json.loads(_read(relative))
    carried = [pointer for pointer in _schema_properties(document)
               if pointer.rsplit("/", 1)[-1] in NAMES]

    assert not carried, (
        f"`{relative}` still publishes the retired inline total:\n"
        + "\n".join(f"  {pointer}" for pointer in carried))


def test_the_column_is_gone_from_the_posting():
    """The column itself, stated separately from the file it lived in.

    The reader gate above would pass on a file that had merely stopped spelling
    it field-shaped. This asks the narrower question the migration answers: is
    there a model field of that name at all?
    """
    source = _read("ubb-platform/apps/metering/usage/models.py")
    declarations = [line.strip() for line in source.splitlines()
                    if re.match(r"\s*(total_)?units\s*=\s*models\.", line)]

    assert not declarations, (
        "the Posting still declares the retired inline total as a column: "
        + "; ".join(declarations))


def test_the_singular_survives_and_still_resolves():
    """The other half of the ruling, and the half a reader will doubt.

    The plural was retired as a sense precisely BECAUSE the singular is this
    slice's own canonical concept, serving a declared measurement's unit. If it
    had gone too, this whole module would be proving a demolition nobody
    ordered.
    """
    registry = load_registry(REAL_REGISTRY, REPO_ROOT)

    assert SINGULAR in registry.concepts, (
        "the singular concept is gone from the registry, so the plural was not "
        "retired in favour of anything")
    assert registry.concepts[SINGULAR].kind == "open"


def test_the_singular_is_still_served_on_the_contract():
    """And it still reaches a tenant.

    A concept that resolves in the registry but appears on no published schema
    would satisfy the test above while the surface it names had quietly gone —
    which is the shape of every absence check this repository has had to repair.
    """
    document = json.loads(_read("openapi/v1.json"))
    marked = json.dumps(document).count(f'"x-ubb-concept": "{SINGULAR}"')

    assert marked, ("no published schema advertises the singular concept, so "
                    "nothing serves what replaced the retired field")


@pytest.mark.parametrize("relative", sorted(READERS) + list(DOCUMENTS))
def test_each_named_reader_was_actually_read(relative):
    """The vacuity guard, per path.

    An absence proved over a file that no longer exists is no proof at all, and
    a renamed module would give exactly that — green, forever, about nothing.
    """
    path = REPO_ROOT / relative
    assert path.is_file(), f"{relative} does not exist"
    assert path.stat().st_size, f"{relative} is empty"


def test_the_control_the_surviving_sense_is_untouched():
    """The positive control, and the statement of scope in one assertion.

    The same matcher, fired at a file that still carries the word field-shaped
    in the rate-arithmetic sense. It must FIND it. That proves two things at
    once: the matcher is not silently matching nothing (without which every
    assertion above is vacuous), and this gate is scoped to a sense rather than
    banning a word the registry says survives in three of them.
    """
    assert FIELD.search(_read(SURVIVING_SENSE)), (
        f"the matcher found nothing in {SURVIVING_SENSE}, where the surviving "
        f"rate-arithmetic sense still spells the word as a receipt key — so it "
        f"would not have found the retired sense either")
    assert SURVIVING_SENSE not in READERS, (
        "the surviving sense's own file was added to the reader list, which "
        "would condemn a spelling no ticket owns")


def test_the_control_above_is_carried_by_the_word_and_not_by_something_else():
    """The control's own control: take the word out and it fails (#370).

    A positive control asserts that the matcher FINDS something. That is worth
    exactly as much as the claim that what it finds is the word — and nothing
    in the assertion above says so, because a matcher that had started matching
    something else entirely in a 1,200-line module would satisfy it just as
    well. Then the day a rename really did empty that file, the control would
    stay green over a subject that had gone, which is the vacuous half of the
    failure slice 4 was warned about by name.

    So the removal is performed rather than argued: every whole-token
    occurrence of the retired names is taken out of the subject's source, and
    the matcher is fired at what is left. It must find nothing. That is the
    ticket's *"remove the word from the subject file and confirm the control
    fails"*, run in-process against the real file, on every run rather than
    once by hand in a window nobody can re-open.
    """
    source = _read(SURVIVING_SENSE)
    assert FIELD.search(source), "the control's own premise has already gone"

    without = re.sub(rf"(?<![0-9A-Za-z_])(?:{_EITHER_NAME})(?![0-9A-Za-z_])",
                     "quantity", source)

    assert not FIELD.search(without), (
        "the matcher still fires on the surviving-sense file with every "
        "occurrence of the word removed — so the control above is passing for "
        "some other reason and would go on passing over an empty subject")


def test_the_control_the_match_is_field_shaped():
    """What the matcher decided, pinned.

    An absence check that over-fires gets suppressed rather than obeyed, and
    this one is aimed at a word with three live senses — so the near misses are
    the point, not a formality.

    THE TWO LISTS COME FROM DIFFERENT PLACES, and saying so is the whole reason
    this docstring exists. The first is every shape the retired field took in the
    readers this commit cleared, quoted from the diff that removed them — they
    are gone from the tree by construction, and a control that required them to
    still be there could never pass. The second is the near misses, which are
    live spellings the tree still carries in senses that survive; the one that
    proves the matcher runs against real code is
    `test_the_control_the_surviving_sense_is_untouched`, which reads a file.
    """
    for field_shaped in ('units = models.BigIntegerField(null=True)',
                         'units=item.units', '"units": e.units',
                         'total_units: int', '{row.units ?? "—"}',
                         'summary["total_units"]', 'the `units` unit'):
        assert FIELD.search(field_shaped), field_shaped

    # ⚠ THE ORDINARY-ENGLISH NEAR MISS MOVED IN #409, and the control below is
    # what forced it. It used to be the `list_tasks` docstring's phrase; that
    # route moved to the root prefix with its description rewritten, so the
    # string stopped being a spelling the tree has. Its replacement is the same
    # sense in the one place it cannot leave from — a GENERATED module,
    # rendered from a concept summary in `domain-vocabulary/`, which the
    # retired-sense entry names as the row that makes this word unremovable by
    # any commit at all.
    #
    # ⚠ AND THE PROSE HERE IS ITSELF SWEPT, so this note deliberately does not
    # SPELL the departed phrase: naming it would put the word back into the
    # tree from the very file explaining that it left.
    for near_miss in ("minor_units", "major_units_decimal", "whole_minor_units",
                      "units_val", "rather than units of work",
                      "per 1K units", "different units, so each ceiling"):
        assert not FIELD.search(near_miss), near_miss


def test_the_control_the_near_misses_are_spellings_the_tree_really_has():
    """And the near misses are real, which is what makes them near misses.

    A list of invented strings would let the matcher tighten until it condemned
    something live, with this control still green. So each one is required to
    appear somewhere the sweep can see — deliberately NOT in the reader list,
    since that is exactly where they must not be.
    """
    surfaces = [_read(relative) for relative in (
        # Currency minor units, rate arithmetic, and the ordinary English inside
        # a generated module — one file per surviving sense, plus the API schema
        # module whose own spellings the matcher must walk past.
        #
        # ⚠ `api/v1/metering_endpoints.py` LEFT THIS LIST IN #409 and was not
        # replaced. It was here for exactly one spelling — the `list_tasks`
        # docstring's, named rather than quoted for the reason given above —
        # and the route carrying it moved to the root prefix with its
        # description rewritten, so the module now holds no occurrence of the
        # word at all. A surface kept in this list after it stops contributing
        # a spelling is a reader that proves nothing, which is the failure this
        # control exists to catch one level down.
        "ubb-platform/core/money.py",
        "ubb-platform/api/v1/schemas.py",
        SURVIVING_SENSE,
        "apps/ui/src/features/pricing/lib/pricing-math.ts",
        "ubb-platform/core/vocabulary.py",
    )]

    for near_miss in ("minor_units", "major_units_decimal", "whole_minor_units",
                      "units_val", "rather than units of work",
                      "per 1K units", "different units, so each ceiling"):
        assert any(near_miss in text for text in surfaces), (
            f"`{near_miss}` is not a spelling the tree has, so requiring the "
            f"matcher to skip it proves nothing about over-firing")
