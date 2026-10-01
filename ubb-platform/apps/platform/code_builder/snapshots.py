"""Storing a resolved Blueprint's content, and reading one back by fingerprint.

Three functions and nothing else may be done with a snapshot: compose its
fingerprint, store it, read it. Plain data in and out, for the reason every
read in the kernel gives — a caller needs what the snapshot says and has no
business holding a record it could save.

**The fingerprint is the hash of the canonical stored content, all of it.**
Nothing is left out of the hash and nothing outside the content is put in: not
the tenant, not the moment of resolution, not a row id. So the same content is
the same fingerprint wherever and whenever it is resolved, and a fingerprint
can be checked by anybody holding the content.

**Canonical means one byte string per value.** Keys sorted, no insignificant
whitespace, text as UTF-8 rather than escaped — so two resolutions that built
the same content in a different key order hash alike, and a declared name
outside ASCII hashes as itself.
"""
import hashlib
import json
import re

from django.db import IntegrityError, transaction

from .models import FINGERPRINT_PATTERN, FINGERPRINT_PREFIX, BlueprintSnapshot

_FINGERPRINT = re.compile(FINGERPRINT_PATTERN)


def canonical(content):
    """`content` as the one byte string its fingerprint is taken over."""
    return json.dumps(content, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def fingerprint_of(content):
    """The `configuration_fingerprint` of `content`: `sha256:` and 64 hex."""
    return FINGERPRINT_PREFIX + hashlib.sha256(canonical(content)).hexdigest()


def is_a_fingerprint(value):
    """Whether `value` is shaped like a fingerprint at all.

    Asked before a lookup so that a path segment which could never name a
    snapshot is answered as one that does not, without a query.
    """
    return isinstance(value, str) and _FINGERPRINT.match(value) is not None


def store(*, tenant, content):
    """Keep `content` for `tenant`, and answer with its fingerprint.

    Idempotent: content already kept is found rather than kept twice, and the
    fingerprint is the same either way. The uniqueness key decides a race — the
    loser of two concurrent first resolutions meets it, in a savepoint of its
    own so the caller's transaction survives, and both answer alike.
    """
    fingerprint = fingerprint_of(content)
    held = BlueprintSnapshot.objects.filter(
        tenant=tenant, configuration_fingerprint=fingerprint)
    if held.exists():
        return fingerprint
    try:
        with transaction.atomic():
            BlueprintSnapshot.objects.create(
                tenant=tenant, configuration_fingerprint=fingerprint,
                content=content)
    except IntegrityError:
        if not held.exists():
            raise
    return fingerprint


def stored(*, tenant, configuration_fingerprint):
    """The content kept for `tenant` under this fingerprint, or `None`.

    `None` covers a fingerprint nobody resolved, one that was pruned, and one
    that is another tenant's — a caller is told the same thing for all three,
    because telling them apart would say whether somebody else's exists.
    """
    if not is_a_fingerprint(configuration_fingerprint):
        return None
    return (BlueprintSnapshot.objects
            .filter(tenant=tenant,
                    configuration_fingerprint=configuration_fingerprint)
            .values_list("content", flat=True).first())
