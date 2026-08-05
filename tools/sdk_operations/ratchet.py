"""The unwrapped count only falls — compared against the base branch, not by habit.

ADR-0007 §4 is precise about what is and is not required here: the number of
published operations with no ergonomic wrapper **need not reach zero**, but any
*increase* "must be an explicit reviewed change rather than an accidental
omission". Those are different obligations from the migration ledger's, and
this module implements the second one only. Nothing here demands the count
shrink; a slice that wraps nothing new is free to merge.

What it refuses is the accident. A slice adds an operation to the spec,
regenerates the manifest, and the count goes up by one inside a 134-row
generated file — visible in the diff, and invisible to a reviewer reading it
the way people read generated files. So the rise itself needs a signature: a
`coverage_authorisations` entry that is **new in this change**, states **how
many** operations it licenses, and says **why**.

Three properties, all borrowed from the ledger's ratchet (#201), because this
is the same problem and a second shape for it would be one more thing to learn:

1. **A rise with no authorisation is refused.** An old authorisation licenses
   nothing later, so the file is an audit trail rather than standing permission.
2. **A miscount is refused.** A reviewer approves a quantity, not an intention.
3. **An authorisation that licenses nothing is refused.** An override that
   overrides nothing is the shape of a check that cannot fail.

The one thing this module does NOT do is recompute the coverage. It compares
the *committed* manifest against the base branch's, exactly as the ledger's
ratchet compares committed ledgers — and `tools.sdk_operations.manifest` has
already proved the committed manifest is what the tree produces. Splitting the
two keeps this the only part that needs git history.
"""

import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml

from tools.sdk_operations import errors as codes
from tools.sdk_operations.errors import SurfaceError
from tools.sdk_operations.manifest import MANIFEST_PATH

#: The hand-authored audit trail of reviewed increases.
AUTHORISATIONS_PATH = "ubb-sdk/coverage-authorisations.yaml"

#: The branch a change lands on, resolved through its merge base — so on a
#: feature branch the comparison is against the manifest the branch started
#: from rather than against whatever main has since become.
DEFAULT_BASE = "origin/main"


@dataclass(frozen=True)
class Comparison:
    """What changed between two manifests, and what the rules say about it."""

    was: int
    now: int
    licensed: int
    faults: tuple

    @property
    def ok(self):
        return not self.faults

    @property
    def rise(self):
        return max(0, self.now - self.was)


def unwrapped_in(document):
    """The unwrapped count a manifest document states, or 0 if it states none.

    Deliberately tolerant. The base branch's manifest is *history*: a branch
    taken before this ticket landed has no manifest at all, and every unwrapped
    operation in the proposal is genuinely an increase from nothing. The head
    manifest's own accuracy is the zero-diff gate's job and has already been
    settled by the time anything here matters.
    """
    summary = (document or {}).get("summary")
    count = summary.get("unwrapped") if isinstance(summary, dict) else None
    return count if isinstance(count, int) else 0


def _authorisations(document):
    """``{id: entries licensed}`` for a parsed authorisations document.

    Keyed on an explicit `id` rather than on the issue number, which is what
    lets one issue authorise twice. A slice landing in two pull requests would
    otherwise find its second rise licensed by the first's entry — standing
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
    was, now = unwrapped_in(base_manifest), unwrapped_in(head_manifest)
    base = _authorisations(base_authorisations)
    head = _authorisations(head_authorisations)
    fresh = {key: count for key, count in head.items() if key not in base}
    licensed = sum(fresh.values())
    rise = max(0, now - was)

    faults = []
    if rise and not fresh:
        faults.append(SurfaceError(
            codes.UNWRAPPED_ROSE, MANIFEST_PATH,
            f"the unwrapped count rose from {was} to {now} with no coverage "
            f"authorisation new in this change. An operation published without "
            f"an ergonomic wrapper is allowed, and being allowed is exactly why "
            f"it has to be said out loud: add an entry to "
            f"{AUTHORISATIONS_PATH} naming an id, the issue, how many "
            f"operations it adds and why."))
    elif rise and licensed != rise:
        faults.append(SurfaceError(
            codes.AUTHORISATION_COUNT_WRONG, AUTHORISATIONS_PATH,
            f"the authorisations new in this change license {licensed} "
            f"operation(s), and the unwrapped count rose by {rise} "
            f"({was} to {now}). A reviewer approves a quantity, not an "
            f"intention."))
    elif not rise and fresh:
        faults.append(SurfaceError(
            codes.AUTHORISATION_INERT, AUTHORISATIONS_PATH,
            f"{', '.join(sorted(fresh))} license {licensed} operation(s) and "
            f"the unwrapped count did not rise ({was} to {now}). An override "
            f"that overrides nothing is the shape of a check that cannot fail "
            f"— delete it, or add the operations it was written for."))

    return Comparison(was=was, now=now, licensed=licensed, faults=tuple(faults))


# ---------------------------------------------------------------------------
# Reading the base ref
# ---------------------------------------------------------------------------

def _git(repo_root, *arguments):
    return subprocess.run(["git", "-C", str(repo_root), *arguments],
                          capture_output=True, text=True)


def resolve_base(repo_root, base=DEFAULT_BASE, proposal_is_committed=True):
    """The commit whose manifest this change is compared against.

    The same resolution `tools/gates/ratchet.py` performs, and for the same
    reasons — including the case where the merge base *is* HEAD, which happens
    two ways that want opposite answers: an uncommitted proposal (HEAD is the
    right baseline) and a commit pushed straight at the base branch (compare
    against its parent, or a direct push would be gated by nothing).

    It never silently skips. A baseline that cannot be read fails the gate.
    """
    merge_base = _git(repo_root, "merge-base", "HEAD", base)
    if merge_base.returncode != 0:
        return None, (f"cannot resolve a merge base with {base!r}: "
                      f"{merge_base.stderr.strip()}. In CI this means the ref "
                      f"was not fetched (`fetch-depth: 0`); the ratchet must "
                      f"never be skipped for a missing baseline.")
    resolved = merge_base.stdout.strip()

    head = _git(repo_root, "rev-parse", "HEAD").stdout.strip()
    if resolved != head or not proposal_is_committed:
        return resolved, None

    parent = _git(repo_root, "rev-parse", "HEAD^")
    if parent.returncode != 0:
        return None, ("HEAD is the merge base, carries the proposed manifest "
                      "and has no parent — there is no earlier manifest to "
                      "compare against.")
    return parent.stdout.strip(), None


def document_at(repo_root, ref, path):
    """The document committed at ``ref``, ``{}`` if the ref never had it.

    A ref that predates this ticket genuinely has no manifest, and every
    unwrapped operation in the proposal genuinely is an increase from nothing.
    ``None`` is reserved for a file that exists and will not parse, which is a
    fault rather than a state.
    """
    result = _git(repo_root, "show", f"{ref}:{path}")
    if result.returncode != 0:
        if ("exists on disk, but not in" in result.stderr
                or "does not exist" in result.stderr):
            return {}
        return None
    try:
        return yaml.safe_load(result.stdout) or {}
    except yaml.YAMLError:
        return None


def _read(repo_root, path):
    target = Path(repo_root) / path
    if not target.is_file():
        return {}
    return yaml.safe_load(target.read_text(encoding="utf-8")) or {}


def run(repo_root, base=DEFAULT_BASE):
    """Resolve the base ref, read both manifests, and compare.

    The proposal is always the WORKING TREE's manifest, so an author gets the
    same verdict before committing that CI gives afterwards.
    """
    repo_root = Path(repo_root)
    head_manifest = _read(repo_root, MANIFEST_PATH)
    head_authorisations = _read(repo_root, AUTHORISATIONS_PATH)

    committed = document_at(repo_root, "HEAD", MANIFEST_PATH)
    ref, problem = resolve_base(repo_root, base,
                                proposal_is_committed=committed == head_manifest)
    if problem is not None:
        return Comparison(0, 0, 0, (SurfaceError(codes.BASE_UNREADABLE,
                                                 MANIFEST_PATH, problem),))

    base_manifest = document_at(repo_root, ref, MANIFEST_PATH)
    base_authorisations = document_at(repo_root, ref, AUTHORISATIONS_PATH)
    if base_manifest is None or base_authorisations is None:
        return Comparison(0, 0, 0, (SurfaceError(
            codes.BASE_UNREADABLE, MANIFEST_PATH,
            f"the coverage manifest or its authorisations at {ref} could not "
            f"be read or parsed."),))
    return compare(base_manifest, head_manifest, base_authorisations,
                   head_authorisations)
