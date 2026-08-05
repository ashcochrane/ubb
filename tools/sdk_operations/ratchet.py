"""No operation becomes unwrapped without a signature.

ADR-0007 §4 is precise about what it does and does not demand: the number of
published operations with no ergonomic wrapper **need not reach zero**, but any
*increase* "must be an explicit reviewed change rather than an accidental
omission". Those are different obligations from the migration ledger's, and this
module implements the second one only. Nothing here demands the count shrink; a
slice that wraps nothing new is free to merge.

What it refuses is the accident. A slice adds an operation to the spec,
regenerates the manifest, and a gap appears inside a 134-row generated file —
visible in the diff, and invisible to a reviewer reading it the way people read
generated files. So the gap needs a signature: a `coverage-authorisations.yaml`
entry that is **new in this change**, states **how many** operations it
licenses, and says **why**.

## Why the set, and not the count

The obvious implementation compares `summary.unwrapped` — two integers. It has
a hole, and the hole is the case a busy slice actually produces: **wrap three
operations and publish two new unwrapped ones, and the net is −1.** No rise, no
signature required, two new gaps merged unreviewed. Worse, a conscientious
author who wrote an authorisation anyway would have it refused as inert.

So the comparison is over the **set of unwrapped operation ids**. Three closed
and two opened is an increase of two, whatever the net does. That is also the
shape the ledger's ratchet already uses — it compares entry *identities*, never
a total — so the two ratchets now differ only where they genuinely disagree.

Three properties, borrowed from the ledger's ratchet (#201) because this is the
same problem and a second shape for it would be one more thing to learn:

1. **A new gap with no authorisation is refused.** An old authorisation licenses
   nothing later, so the file is an audit trail rather than standing permission.
2. **A miscount is refused.** A reviewer approves a quantity, not an intention.
3. **An authorisation that licenses nothing is refused.** An override that
   overrides nothing is the shape of a check that cannot fail.

The one thing this module does NOT do is recompute the coverage. It compares the
*committed* manifest against the base branch's, exactly as the ledger's ratchet
compares committed ledgers — and `tools.sdk_operations.manifest` has already
proved the committed manifest is what the tree produces. Splitting the two keeps
this the only part that needs git history.
"""

from dataclasses import dataclass

from tools.ratchets import (
    DEFAULT_BASE, document_at, resolve_base, working_tree_document,
)
from tools.sdk_operations import errors as codes
from tools.sdk_operations.coverage import WRAPPED
from tools.sdk_operations.errors import SurfaceError
from tools.sdk_operations.manifest import MANIFEST_PATH

#: The hand-authored audit trail of reviewed increases.
AUTHORISATIONS_PATH = "ubb-sdk/coverage-authorisations.yaml"

__all__ = ["AUTHORISATIONS_PATH", "Comparison", "DEFAULT_BASE", "compare",
           "run", "unwrapped_ids"]


@dataclass(frozen=True)
class Comparison:
    """What changed between two manifests, and what the rules say about it."""

    opened: tuple           # operations that became unwrapped
    closed: tuple           # operations that gained a wrapper
    licensed: int
    faults: tuple

    @property
    def ok(self):
        return not self.faults

    @property
    def rise(self):
        return len(self.opened)


def unwrapped_ids(document):
    """Every operation a manifest document says has no ergonomic wrapper.

    Read from the rows rather than from `summary.unwrapped`, so the comparison
    is over identities and a count that disagreed with its own table could not
    decide anything.

    Deliberately tolerant. The base branch's manifest is *history*: a branch
    taken before this ticket landed has no manifest at all, and every gap in the
    proposal is genuinely new. The head manifest's own accuracy is the zero-diff
    gate's job and has already been settled by the time anything here matters.
    """
    found = set()
    for row in (document or {}).get("operations") or []:
        if not isinstance(row, dict):
            continue
        operation_id, disposition = row.get("operation_id"), row.get("disposition")
        if isinstance(operation_id, str) and disposition != WRAPPED:
            found.add(operation_id)
    return found


def _authorisations(document):
    """``{id: operations licensed}`` for a parsed authorisations document.

    Keyed on an explicit `id` rather than on the issue number, which is what
    lets one issue authorise twice. A slice landing in two pull requests would
    otherwise find its second gap licensed by the first's entry — standing
    permission wearing an audit trail's clothes.
    """
    licensed = {}
    for body in (document or {}).get("authorisations") or []:
        if not isinstance(body, dict):
            continue
        key, count = body.get("id"), body.get("operations_added")
        if isinstance(key, str) and isinstance(count, int):
            licensed[key] = count
    return licensed


def compare(base_manifest, head_manifest, base_authorisations,
            head_authorisations):
    """The verdict on the proposed manifest, given the base branch's.

    Pure, over four parsed documents, so the negative controls put synthetic
    manifests through the same entry point CI uses.
    """
    was, now = unwrapped_ids(base_manifest), unwrapped_ids(head_manifest)
    opened, closed = tuple(sorted(now - was)), tuple(sorted(was - now))

    base = _authorisations(base_authorisations)
    fresh = {key: count for key, count in _authorisations(head_authorisations).items()
             if key not in base}
    licensed = sum(fresh.values())

    faults = []
    if opened and not fresh:
        faults.append(SurfaceError(
            codes.UNWRAPPED_ROSE, MANIFEST_PATH,
            f"{len(opened)} operation(s) became unwrapped with no coverage "
            f"authorisation new in this change: {', '.join(opened)}. "
            f"Publishing an operation without an ergonomic wrapper is allowed, "
            f"and being allowed is exactly why it has to be said out loud: add "
            f"an entry to {AUTHORISATIONS_PATH} naming an id, the issue, how "
            f"many operations it adds and why."))
    elif opened and licensed != len(opened):
        faults.append(SurfaceError(
            codes.AUTHORISATION_COUNT_WRONG, AUTHORISATIONS_PATH,
            f"the authorisations new in this change license {licensed} "
            f"operation(s), and {len(opened)} became unwrapped "
            f"({', '.join(opened)}). A reviewer approves a quantity, not an "
            f"intention."))
    elif not opened and fresh:
        faults.append(SurfaceError(
            codes.AUTHORISATION_INERT, AUTHORISATIONS_PATH,
            f"{', '.join(sorted(fresh))} license {licensed} operation(s) and "
            f"no operation became unwrapped. An override that overrides "
            f"nothing is the shape of a check that cannot fail — delete it, or "
            f"add the operations it was written for."))

    return Comparison(opened=opened, closed=closed, licensed=licensed,
                      faults=tuple(faults))


def run(repo_root, base=DEFAULT_BASE):
    """Resolve the base ref, read both manifests, and compare.

    The proposal is always the WORKING TREE's manifest, so an author gets the
    same verdict before committing that CI gives afterwards.
    """
    head_manifest = working_tree_document(repo_root, MANIFEST_PATH)
    head_authorisations = working_tree_document(repo_root, AUTHORISATIONS_PATH)

    committed = document_at(repo_root, "HEAD", MANIFEST_PATH)
    ref, problem = resolve_base(repo_root, base,
                                proposal_is_committed=committed == head_manifest)
    if problem is not None:
        return Comparison((), (), 0, (SurfaceError(codes.BASE_UNREADABLE,
                                                   MANIFEST_PATH, problem),))

    base_manifest = document_at(repo_root, ref, MANIFEST_PATH)
    base_authorisations = document_at(repo_root, ref, AUTHORISATIONS_PATH)
    if base_manifest is None or base_authorisations is None:
        return Comparison((), (), 0, (SurfaceError(
            codes.BASE_UNREADABLE, MANIFEST_PATH,
            f"the coverage manifest or its authorisations at {ref} could not "
            f"be read or parsed."),))
    return compare(base_manifest, head_manifest, base_authorisations,
                   head_authorisations)
