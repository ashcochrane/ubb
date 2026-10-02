"""A token's name splits into the segments it was built from, whatever a
tenant called their key (#576, ADR-0015 §3).

The owner's condition on the naming convention (review of PR #594): one
encode and one decode, and the round trip and the absence of collisions
pinned — for the separator, for the sign the encoding uses, for the two mixed,
and for ordinary keys outside ASCII.

No database and no route: these are properties of two functions. What a
Blueprint actually answers with is held through the API, in
``api/v1/tests/test_the_integration_blueprint.py``.
"""
import itertools

import pytest

from apps.platform.code_builder.token_names import (
    SEPARATOR, key_of, name, segment)

#: Keys chosen for what they do to the encoding rather than for realism.
AWKWARD_KEYS = [
    # the separator
    ".", "a.b", ".a", "a.", "a..b", "tokens.source_path",
    # the sign the encoding uses
    "%", "100%", "%%", "a%b",
    # the two mixed, in both orders and adjacent
    "%.", ".%", "a.b%c", "a%b.c", "%.%.",
    # keys that already LOOK encoded, and their own encodings
    "%2E", "%25", "%252E", "%2525", "a%2Eb", "%2e", "2E", "25",
    # ordinary keys outside ASCII, with and without the two characters
    "café", "naïve.tokens", "入力トークン", "入力.トークン", "größe 100%", "ключ",
    # keys the encoding leaves alone
    "input_tokens", "cache-read tokens", "a b", "O'Brien", "$cost", "a/b",
    "a:b", "",
]


@pytest.mark.parametrize("key", AWKWARD_KEYS)
def test_a_key_comes_back_from_its_segment_exactly(key):
    assert key_of(segment(key)) == key


@pytest.mark.parametrize("key", AWKWARD_KEYS)
def test_a_segment_never_contains_the_separator(key):
    assert SEPARATOR not in segment(key)


def test_no_two_keys_share_a_segment():
    """Pairwise, over every key above. The ones that would collide under a
    weaker encoding are in the list on purpose: a key with a dot and the same
    key already encoded, and that key's own encoding."""
    segments = {key: segment(key) for key in AWKWARD_KEYS}

    assert len(set(segments.values())) == len(AWKWARD_KEYS)
    for one, other in itertools.combinations(AWKWARD_KEYS, 2):
        assert segments[one] != segments[other], (one, other)


def test_the_keys_that_would_collide_are_the_ones_being_told_apart():
    """The control: without the sign being encoded, these three are one."""
    def separator_only(key):
        return key.replace(".", "%2E")

    assert separator_only("a.b") == separator_only("a%2Eb")
    assert len({segment("a.b"), segment("a%2Eb"), segment("a%252Eb")}) == 3
    assert (segment("a.b"), segment("a%2Eb")) == ("a%2Eb", "a%252Eb")


def test_a_key_with_neither_character_is_its_own_segment():
    for key in ("input_tokens", "cache-read tokens", "café", "入力トークン",
                "O'Brien"):
        assert segment(key) == key


@pytest.mark.parametrize("key", AWKWARD_KEYS)
def test_a_name_splits_into_the_segments_it_was_built_from(key):
    """The field, the key and the element, whatever the key holds — so a key
    that ends like an element is never taken for one."""
    field, key_segment, element = name(
        "measurements", key, "source_path").split(SEPARATOR)

    assert (field, key_of(key_segment), element) == (
        "measurements", key, "source_path")
    assert name("measurements", key).split(SEPARATOR) == [
        "measurements", key_segment]


def test_a_name_without_a_key_is_the_published_names_as_they_are():
    assert name("task_type") == "task_type"
    assert name("task_type", element="pricing_mode") == "task_type.pricing_mode"


def test_a_value_under_one_key_and_a_fact_under_another_never_share_a_name():
    """The collision the encoding exists for: the VALUE under a key that ends
    like an element, and that ELEMENT under the key it ends like."""
    assert (name("measurements", "tokens.source_path")
            != name("measurements", "tokens", "source_path"))
