"""How a token of an Integration Blueprint is named: the one implementation.

A token's name says where on a call it sits, as one to three segments joined
by a dot — the field, a declared key under it, a declared fact about that
(ADR-0015 §3). A declared key is the tenant's own word and may contain
anything, the separator included, so a key is ENCODED into its segment. This
module is the whole of that encoding, in both directions, and nothing else
spells it.

**The encoding.** Two characters and no more: the separator, and the sign the
encoding itself uses.

    %  ->  %25
    .  ->  %2E

Everything else — a space, a hyphen, a letter outside ASCII — is its own
character in the segment. So a key with neither character is its own segment,
which is nearly all of them, and a name reads as the tenant wrote it.

**What it guarantees**, and `tests/test_token_names.py` holds each:

* a segment never contains the separator, so a name always splits on its dots
  into exactly the segments it was built from;
* two different keys never share a segment, so two tokens never share a name
  by accident — including a key that already looks encoded;
* decoding a segment gives back the key, exactly.

**A consumer does not need the encoding to pair tokens.** A key's own token
carries the key unencoded, as its literal, and the tokens named under that key
follow it directly, sharing one `<field>.<segment>` prefix. A renderer reads
the prefix off the name it was given. `key_of` is here so the encoding is
stated once with its inverse beside it, and so anything written in this
repository that must go from a name back to a key has one place to ask.
"""
import re

#: What joins the segments of a name.
SEPARATOR = "."

#: The sign the encoding uses, and what each encoded character becomes. The
#: sign is first: it is encoded before the separator is, so the sign an
#: encoded separator introduces is not encoded a second time.
_ESCAPE = "%"
_ENCODED = {_ESCAPE: "%25", SEPARATOR: "%2E"}
_DECODED = {encoded: character for character, encoded in _ENCODED.items()}

#: One pass, left to right, over exactly the two sequences the encoding
#: writes. Two successive replacements would be wrong here: the second could
#: read a sequence the first had just produced.
_AN_ENCODED_CHARACTER = re.compile("|".join(map(re.escape, _DECODED)))


def segment(key):
    """A declared key as ONE segment of a token's name."""
    for character, encoded in _ENCODED.items():
        key = key.replace(character, encoded)
    return key


def key_of(encoded_segment):
    """The declared key a segment stands for: the inverse of :func:`segment`."""
    return _AN_ENCODED_CHARACTER.sub(lambda found: _DECODED[found.group()],
                                     encoded_segment)


def name(field, key=None, element=None):
    """A token's name: the field, then the key under it, then the element.

    `field` and `element` are published field names and are joined as they
    are; only `key` is the tenant's, so only `key` is encoded.
    """
    segments = [field]
    if key is not None:
        segments.append(segment(key))
    if element is not None:
        segments.append(element)
    return SEPARATOR.join(segments)
