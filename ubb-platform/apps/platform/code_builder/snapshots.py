"""Storing a resolved Blueprint's content, and reading one back by fingerprint.

What may be done with a snapshot is compose its fingerprint, store it and read
it, and this module is all of it. Plain data in and out, for the reason every
read in the kernel gives — a caller needs what the snapshot says and has no
business holding a record it could save.

THE HASH BOUNDARY
-----------------
A snapshot's content has two halves, and **the fingerprint is the hash of one
of them** (owner ruling of 2026-10-02, on PR #594).

* **`identity`** — the normative resolved contract: what was selected, the
  machine-readable resolution of it, the configuration it was resolved from
  with the publication each part came from, and the versions needed to read
  it. A generated file is stamped with the hash of this, so this is what the
  file claims it was generated from.
* **`presentation`** — what is kept so the Blueprint can be returned as it was
  answered, and is NOT part of what it means: today, the ready-to-copy request
  a diagnostic offers. It is derived from the API's own routes and request
  shapes rather than from the tenant's configuration, so a route gaining a
  field must not make every blocked integration look like a different one.

So the fingerprint is a stable identity of the resolved contract, never "a
hash of every byte that happened to be serialised". What goes in which half is
the resolver's to decide and to defend (`api/v1/integration_blueprint.py`);
what this module guarantees is that only the first half is hashed, all of it,
and nothing from outside it — not the tenant, not the moment, not a row id.

**Canonical means one byte string per value.** Keys sorted, no insignificant
whitespace, text as UTF-8 rather than escaped — so two resolutions that built
the same identity in a different key order hash alike, and a declared name
outside ASCII hashes as itself. A LIST is ordered and its order is hashed, so
a list whose order means nothing must reach here already in a canonical
order; that too is the resolver's.

**Storing is first-wins on presentation.** A snapshot is found by its
fingerprint, so an identity already kept is not kept again — and the
presentation beside it is the one it was first stored with.

HOW LONG ONE IS KEPT
--------------------
:data:`RETENTION` after it was last RESOLVED (#580). Storing an identity that
is already kept restarts the period, so a developer who generates again from
unchanged configuration — and is handed the same fingerprint — is not handed
one that is about to go. Reading a snapshot and verifying one do not restart
it: both are reads of something the developer already holds.

Thirty days because the snapshot exists for one job — proving that the code a
developer just generated records and costs — and that happens while they are
writing it. It is bounded at all because resolving is a READ-floor act, so
anybody holding any key can add a snapshot. The period is the owner's
(approved on the review of #599).

⚠ **WHAT A PRUNE COSTS, SAID PLAINLY.** A fingerprint is readable and
verifiable for thirty days after its most recent resolution. After it is
pruned, resolving the selection again recreates THAT fingerprint only if the
configuration still resolves to exactly the same normative content —
including which publication each Event Type came from. If anything it covers
has changed, resolving again correctly gives a different fingerprint, and a
file stamped with the pruned one can no longer be verified: it must be
generated again.
"""
import hashlib
import json
import re
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import FINGERPRINT_PATTERN, FINGERPRINT_PREFIX, BlueprintSnapshot

#: How long a snapshot is kept after it was last resolved.
RETENTION = timedelta(days=30)

_FINGERPRINT = re.compile(FINGERPRINT_PATTERN)

#: The two halves of a snapshot's content, by the keys they are kept under.
IDENTITY = "identity"
PRESENTATION = "presentation"


def canonical(identity):
    """`identity` as the one byte string its fingerprint is taken over."""
    return json.dumps(identity, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def fingerprint_of(identity):
    """The `configuration_fingerprint` of `identity`: `sha256:` and 64 hex."""
    return FINGERPRINT_PREFIX + hashlib.sha256(canonical(identity)).hexdigest()


def is_a_fingerprint(value):
    """Whether `value` is shaped like a fingerprint at all.

    Asked before a lookup so that a path segment which could never name a
    snapshot is answered as one that does not, without a query.
    """
    return isinstance(value, str) and _FINGERPRINT.match(value) is not None


def store(*, tenant, identity, presentation):
    """Keep a resolution for `tenant`, and answer with its fingerprint.

    The fingerprint is of `identity` alone. Idempotent: an identity already
    kept is found rather than kept twice, and the fingerprint is the same
    either way. The uniqueness key decides a race — the loser of two
    concurrent first resolutions meets it, in a savepoint of its own so the
    caller's transaction survives, and both answer alike.

    Finding it kept restarts its retention period, and writes nothing else:
    the content is frozen, and the moment it was last resolved is not part
    of it.
    """
    fingerprint = fingerprint_of(identity)
    held = BlueprintSnapshot.objects.filter(
        tenant=tenant, configuration_fingerprint=fingerprint)
    if held.update(updated_at=timezone.now()):
        return fingerprint
    try:
        with transaction.atomic():
            BlueprintSnapshot.objects.create(
                tenant=tenant, configuration_fingerprint=fingerprint,
                content={IDENTITY: identity, PRESENTATION: presentation})
    except IntegrityError:
        if not held.exists():
            raise
    return fingerprint


def stored(*, tenant, configuration_fingerprint):
    """The content kept for `tenant` under this fingerprint — both halves, by
    :data:`IDENTITY` and :data:`PRESENTATION` — or `None`.

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


def prune(*, now=None):
    """Delete every snapshot, of every tenant, not resolved within
    :data:`RETENTION`. Returns how many went."""
    cutoff = (now or timezone.now()) - RETENTION
    pruned, _ = BlueprintSnapshot.objects.filter(updated_at__lt=cutoff).delete()
    return pruned
