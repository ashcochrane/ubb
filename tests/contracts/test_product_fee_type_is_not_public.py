"""`ProductFeeConfig.fee_type` has no registry concept, and why (#227, story 15).

#206 moved `flat`, `hold` and `estimate` out of the forbidden-term sweep's input
because between them they produced 1,069 hits and almost none was the retired
sense. It recorded that the move costs exactly one live occurrence:
`ProductFeeConfig.fee_type == "flat"` **is** the retired sense, and after the
move *"no gate sees it — G7 because the word is no longer input, G2 because
`fee_type` is a bare CharField the registry declares no concept for."*

#191 story 15 gives two ways out: give it a concept, or record why it has none.
It has none, and the reason is that story 15's premise does not hold for it —
**it is not a public value set.** It appears in no committed contract, no SDK
and no console. It is UBB's own platform-fee configuration, written by
operators through no API at all, and read in exactly one service.

Declaring it would cost two things worth refusing. It would put a private
operator field into `domain-vocabulary/`, which is the checked-in statement of
the **agreed model** rather than an inventory of every column; and — because
`flat` is retired in this sense — it would mean coining a replacement name for a
subject no slice in #194's table rebuilds, which is a naming act ADR-0006 owns
and this ticket does not.

**So the claim is put under test rather than written down.** The manifest's G2
row says `fee_type` gets no concept *because it is not public*; this module is
what makes that falsifiable. The day it reaches the spec, the SDK or the
console, story 15 binds, this fails, and the concept is owed by whoever
published it.

What this is NOT is a check that `fee_type` is correct. It carries an
undeclared value set with a retired sense in it, and one of its values —
`flat_monthly`, which the tests create and the service matches nowhere — falls
through to a silent `continue`. That is a real defect and it belongs to whoever
rebuilds the platform fee; recording it here is the point of the module, not an
oversight in it.
"""

import re

import pytest

from _helpers import REPO_ROOT

#: The field, and the model it sits on.
FIELD = "fee_type"
MODEL = "ubb-platform/apps/billing/tenant_billing/models.py"

#: The field as a WHOLE TOKEN. `platform_fee_type` and `fee_types` are
#: different identifiers, and matching them would make the gate fire on names
#: that have nothing to do with this one. Same rule the forbidden-term sweep
#: applies, and for the same reason — an over-firing absence check gets
#: suppressed rather than obeyed.
TOKEN = re.compile(rf'(?<![0-9A-Za-z_]){re.escape(FIELD)}(?![0-9A-Za-z_])')

#: The three surfaces that make a value set public. Exactly the surfaces
#: `domain-vocabulary/consumers.yaml` declares beside `backend` — a value a
#: tenant can see in the contract, name in the SDK or read in the console.
PUBLIC = {
    "the committed contract": "openapi/v1.json",
    "the SDK": "ubb-sdk/ubb",
    "the console": "apps/ui/src",
}


def _sources(relative):
    path = REPO_ROOT / relative
    if path.is_file():
        return [path]
    return [child for child in sorted(path.rglob("*"))
            if child.is_file() and child.suffix in {".py", ".ts", ".tsx",
                                                    ".json"}]


def test_the_undeclared_fee_type_reaches_no_public_surface():
    """THE GATE. `fee_type` is private, so story 15 does not bind to it.

    A whole-word match, and deliberately a textual one: this is not the
    consumer census, which may never compare spellings (#191 decision 3). Here
    the question genuinely IS textual — has this identifier appeared on a
    surface a tenant reads? — and there is no artifact to hold it by reference
    to, because the whole finding is that it has no concept.
    """
    found = []
    for surface, relative in sorted(PUBLIC.items()):
        for path in _sources(relative):
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if TOKEN.search(text):
                found.append(f"{surface}: {path.relative_to(REPO_ROOT)}")

    assert not found, (
        f"`{FIELD}` has reached a public surface, so it is now a public value "
        f"set and #191 story 15 binds: give it a concept in "
        f"`domain-vocabulary/`, declare its consumers, and delete this test "
        f"along with the paragraph in G2's manifest row that points at it.\n"
        + "\n".join(f"  {where}" for where in found))


def test_the_field_this_is_about_still_exists():
    """A vacuity guard, and not a formality.

    Every assertion above is an absence. If `fee_type` were renamed or deleted,
    the gate would pass forever while proving nothing, and G2's manifest row
    would go on explaining why a field nobody has has no concept.
    """
    text = (REPO_ROOT / MODEL).read_text(encoding="utf-8")
    assert f"{FIELD} = models.CharField" in text, (
        f"`{FIELD}` is no longer a CharField on {MODEL}. If it gained "
        f"`choices` or a registry concept, delete this module and G2's "
        f"paragraph about it; if it was deleted, #206's recorded residue is "
        f"discharged and the same applies.")


def test_the_field_still_declares_no_value_set_of_its_own():
    """The other half of the finding: it is a BARE `CharField`.

    A `choices` list would make it a declared enumeration, which is a different
    situation with a different answer — visible to a reader, and to whichever
    gate covers declared value sets when one does.
    """
    text = (REPO_ROOT / MODEL).read_text(encoding="utf-8")
    line = next(l for l in text.splitlines() if f"{FIELD} = models.CharField" in l)
    assert "choices" not in line, (
        f"`{FIELD}` now declares its own value set: {line.strip()}")


@pytest.mark.parametrize("surface", sorted(PUBLIC))
def test_each_public_surface_was_actually_read(surface):
    """#191 story 20's vacuity guard, per surface.

    An absence test whose walk resolved nothing is a test that passes on
    nothing — the shape this repository has shipped three times. So each
    surface must yield files, and they must be files with content.
    """
    sources = _sources(PUBLIC[surface])
    assert sources, f"{surface} ({PUBLIC[surface]}) resolved to no files"
    assert any(path.stat().st_size for path in sources)


#: A field that IS public, for the positive control below. A registry concept
#: (`free_text`) whose declared consumers include the committed contract, and
#: which a tenant meets on all three surfaces — so a search that cannot find it
#: could not have found `fee_type` either.
PUBLIC_FIELD = "external_task_id"


def test_the_control_a_field_that_is_public_is_found():
    """The positive control. Without it, everything above is green over a
    matcher that reads nothing — an absence proved by a search that never
    ran."""
    token = re.compile(rf'(?<![0-9A-Za-z_]){PUBLIC_FIELD}(?![0-9A-Za-z_])')
    for surface, relative in sorted(PUBLIC.items()):
        assert any(token.search(path.read_text(encoding="utf-8",
                                               errors="ignore"))
                   for path in _sources(relative)), (
            f"the search found no `{PUBLIC_FIELD}` on {surface}, so it would "
            f"not have found `{FIELD}` either")


def test_the_control_the_match_is_a_whole_token():
    """`platform_fee_type` and `fee_types` are different identifiers.

    Pinned so a change to the matcher has to come past a test that says what it
    decided — an over-firing absence check is one that gets suppressed rather
    than obeyed.
    """
    assert TOKEN.search("fee_type = models.CharField()")
    assert TOKEN.search('{"fee_type": "percentage"}')
    for near_miss in ("platform_fee_type", "fee_types", "feetype", "xfee_typex"):
        assert not TOKEN.search(near_miss), near_miss
