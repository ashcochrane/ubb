"""Reading the base ref — the half every ratchet in this repository shares.

A ratchet asks one question: *is the proposed state worse than the state this
change branched from?* Answering it needs a baseline, and resolving a baseline
from git is fiddly in exactly the same way every time. #201's migration ledger
and #204's SDK coverage manifest both need it; a third will too.

So it lives here once. The alternative — and what #204 first shipped — is two
near-verbatim copies differing only in whether the prose says "ledger" or
"manifest", which is the arrangement `ubb-sdk/ubb/_http.py` already exists to
refuse: *"so the product clients share one implementation instead of two copies
that can drift."* A drift here would be worse than in a client, because the
thing that drifts is whether a gate compares against anything at all.

What each ratchet keeps for itself is its *comparison* — what counts as worse.
That genuinely differs: the ledger may not grow at all, while the coverage
manifest may hold any number of gaps and only refuses new ones.

**It never silently skips.** A baseline that cannot be read fails the gate.
`openapi/contract_gate.py` made the same call, for the same reason: a
comparison that quietly passes when it could not run is indistinguishable from
one that ran and found nothing.
"""

import subprocess
from pathlib import Path

import yaml

#: The branch a change lands on. Resolved through its merge base, so on a
#: feature branch the comparison is against the state the branch started from
#: rather than against whatever main has since become.
DEFAULT_BASE = "origin/main"


def git(repo_root, *arguments):
    """One git command in ``repo_root``, returning the completed process."""
    return subprocess.run(["git", "-C", str(repo_root), *arguments],
                          capture_output=True, text=True)


def resolve_base(repo_root, base=DEFAULT_BASE, proposal_is_committed=True):
    """``(ref, problem)`` — the commit this change is compared against.

    The merge base with ``base``: on a feature branch, the state the branch
    started from; on a pull request, the base branch's, because the checkout is
    a merge commit.

    The one case needing care is when the merge base *is* HEAD, which happens
    two ways that want opposite answers:

    - the proposal is uncommitted, sitting in the working tree. HEAD is exactly
      the right baseline, and there is nothing else it could be.
    - the proposal IS HEAD — a commit pushed straight to the base branch.
      Comparing it against itself would prove nothing, so this falls back to the
      first parent and asks "did this commit make things worse?" A direct push
      is gated like anything else.
    """
    merge_base = git(repo_root, "merge-base", "HEAD", base)
    if merge_base.returncode != 0:
        return None, (f"cannot resolve a merge base with {base!r}: "
                      f"{merge_base.stderr.strip()}. In CI this means the ref "
                      f"was not fetched (`fetch-depth: 0`); the ratchet must "
                      f"never be skipped for a missing baseline.")
    resolved = merge_base.stdout.strip()

    head = git(repo_root, "rev-parse", "HEAD").stdout.strip()
    if resolved != head or not proposal_is_committed:
        return resolved, None

    parent = git(repo_root, "rev-parse", "HEAD^")
    if parent.returncode != 0:
        return None, ("HEAD is the merge base, carries the proposal and has no "
                      "parent — there is no earlier state to compare against.")
    return parent.stdout.strip(), None


def document_at(repo_root, ref, path):
    """The YAML document committed at ``ref``, or ``{}``, or ``None``.

    Three outcomes, and the difference between the last two is the whole point:

    - the document, parsed;
    - ``{}`` — the ref never had the file. That is the true state of a branch
      taken before the gate existed, and everything in the proposal is
      genuinely new;
    - ``None`` — the file is there and will not parse. A fault, not a state,
      and the caller must fail rather than treat it as an empty baseline.

    Deliberately tolerant of a document that would fail today's schema: the
    base ref is *history*, and history that has since been re-shaped must not
    stop today's comparison from running. The proposal's own validity is the
    compiler's job, and it has already run by the time anything here matters.
    """
    result = git(repo_root, "show", f"{ref}:{path}")
    if result.returncode != 0:
        if ("exists on disk, but not in" in result.stderr
                or "does not exist" in result.stderr):
            return {}
        return None
    try:
        return yaml.safe_load(result.stdout) or {}
    except yaml.YAMLError:
        return None


def working_tree_document(repo_root, path):
    """The document as it sits in the working tree, or ``{}`` if absent.

    The proposal is always read from the working tree rather than from HEAD, so
    an author gets the same verdict before committing that CI gives afterwards.
    """
    target = Path(repo_root) / path
    if not target.is_file():
        return {}
    return yaml.safe_load(target.read_text(encoding="utf-8")) or {}
