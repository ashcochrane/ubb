"""The split published four schemas and owes the registry nothing (#368).

⚠ **THIS CLAIM WAS MADE IN A COMMIT MESSAGE AND NOWHERE A READER COULD CHECK
IT**, which is the shape of every marker mistake this programme has paid for.
The reasoning was: a book's identity, the supplier it records and the currency
it is written in are all OPEN strings — a tenant coins the key, the supplier
list is the world's and the currency set is ISO's — so none of the four schemas
the container's split published declares a value set the registry governs, no
`x-ubb-concept` marker is owed on any of them, and none was added. That is a
true sentence about a generated document, so it can be read off the document.

**AND THE WEBHOOK SECTION IS THE HALF MOST EASILY MISSED.** `openapi/v1.json`
carries a `webhooks` block that no route table walks, so a marker owed there
can be absent for a whole slice without any path-shaped check noticing. The
split moved no outbox payload, so the markers there must be exactly the two
that were there before it — on the usage callback, about the two statuses a
recorded event resolves to — and none of them may name a book.

⚠ **THE NEGATIVE CONTROL IS THE POINT OF THE MODULE.** "No marker found" is
what a walk over the wrong node also reports. `test_the_walk_finds_the_markers_
that_ARE_owed` fires the same walk at the whole document and requires the known
population, so a walk that stopped working could not pass the two absences.

This is a document test rather than a code test on purpose: what a client
generator, the console's snapshot and every SDK see is the committed JSON, and
a marker that a Python annotation intends but the exporter drops is invisible
to anything that reads the annotation.
"""

import json

import pytest

from _helpers import REPO_ROOT

MARKER = "x-ubb-concept"

#: The four schemas the container's split published. Named rather than matched
#: on a substring, because "every schema whose name contains Book" also catches
#: the change and publish bodies #367 added — which DO carry markers, legally,
#: and would make this module fail for a reason that is not its subject.
THE_SCHEMAS_THE_SPLIT_PUBLISHED = (
    "PricingBookIn",
    "PricingBookOut",
    "CostBookIn",
    "CostBookOut",
)

#: What the webhook block is allowed to mark, and where. Both belong to the
#: usage callback and both are about a recorded event's own resolution, which
#: is the population that was there before this slice and must be after it.
THE_WEBHOOK_MARKERS_THAT_PREDATE_THE_SPLIT = {
    ("usage.recorded", "costing_status"),
    ("usage.recorded", "pricing_status"),
}


@pytest.fixture(scope="module")
def spec():
    return json.loads(
        (REPO_ROOT / "openapi" / "v1.json").read_text(encoding="utf-8"))


def _marked(node, path=""):
    """Every (json-pointer, concept) pair below `node`, however deep.

    Structural rather than textual: a marker inside an `anyOf` branch of an
    optional property is the ordinary shape for a nullable enum here, and a
    check that only read `properties/<name>` would miss every one of them.
    """
    found = []
    if isinstance(node, dict):
        if MARKER in node:
            found.append((path, node[MARKER]))
        for key, value in node.items():
            found.extend(_marked(value, f"{path}/{key}"))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found.extend(_marked(value, f"{path}/{index}"))
    return found


# ---------------------------------------------------------------------------
# 1. The four schemas owe nothing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", THE_SCHEMAS_THE_SPLIT_PUBLISHED)
def test_a_published_book_schema_declares_no_governed_value_set(spec, name):
    schema = spec["components"]["schemas"].get(name)

    assert schema is not None, (
        f"{name} is not in the contract, so this module is asserting nothing "
        f"about it — the schema was renamed and this list was not")
    assert _marked(schema) == [], (
        f"{name} now marks a governed concept. That is not a failure by "
        f"itself: it means a value set arrived on the book surface, and it "
        f"owes `domain-vocabulary/` a concept, `en.json` a wording per value "
        f"and this module a new sentence")


def test_the_walk_finds_the_markers_that_ARE_owed(spec):
    """The control. Every assertion above is an absence, and an absence is what
    a walk pointed at the wrong node reports too."""
    everything = _marked(spec)

    assert len(everything) > 20, (
        "the walk found almost nothing across the whole contract, so the two "
        "absences above prove nothing about books")
    assert any("/BookChangeIn/" in path for path, _ in everything), (
        "the body that DECLARES a change to a book carries a governed method "
        "and a governed arithmetic shape (#367). A walk that cannot see those "
        "cannot see one arriving on the four schemas above either")


# ---------------------------------------------------------------------------
# 2. The webhook block moved no payload
# ---------------------------------------------------------------------------

def test_the_webhook_block_carries_exactly_the_markers_it_did_before(spec):
    """Read off the document rather than off the outbox, because the callback
    schemas are generated from payload classes and a change to one lands here
    whether or not anybody thought of this file."""
    seen = set()
    for event_name, node in spec.get("webhooks", {}).items():
        for path, concept in _marked(node):
            seen.add((event_name, concept))

    assert seen == THE_WEBHOOK_MARKERS_THAT_PREDATE_THE_SPLIT


def test_no_webhook_marker_names_a_book(spec):
    """The narrower claim, said separately so a future callback that legally
    adds an unrelated marker fails the test above — which asks a maintainer to
    look — rather than this one, which would then be silently widened."""
    for event_name, node in spec.get("webhooks", {}).items():
        for path, concept in _marked(node):
            assert "book" not in concept.lower(), (
                f"the {event_name} callback marks {concept!r}. A book concept "
                f"reaching a payload means the split's entities crossed into "
                f"the outbox, which this slice deliberately did not do")
            assert "book" not in path.lower(), (
                f"the {event_name} callback carries a marked field under "
                f"{path}, which names a book")
