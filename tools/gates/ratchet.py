"""The ledger only shrinks — compared against the base branch, not by habit.

The migration ledger is a finite migration plan that reaches zero at slice 8,
before platform admission. That only holds if growth is mechanically refused,
so this module answers one question: *does the proposed ledger owe more than the
base branch's did?*

It is the same ratchet shape the repository already runs — the spec drift gate
and the SDK regeneration gates make the committed state the floor and compare
against a baseline. Three ways a ledger can grow, and all three are caught:

1. **An entry appears.** Refused, unless a seeding authorisation naming that
   gate is NEW in this change — the explicit, reviewed override. An old
   authorisation cannot license a later addition, so the list of them is an
   audit trail rather than standing permission.
2. **An authorisation miscounts.** It states how many entries it licenses, and
   that number must be exactly how many arrived. A reviewer approves a quantity,
   not an intention.
3. **A debt is quietly deferred.** An entry that stays but whose owner slice
   moves later has not shrunk anything; it has been pushed towards the cutover,
   which is #155 §17's failure with an extra step. Moving it earlier is free.

Removals are always fine. That is the whole point.
"""

from dataclasses import dataclass

from tools.gates import errors as codes
from tools.gates.compiler import LEDGER_FILE
from tools.gates.errors import GateError
from tools.ratchets import (
    DEFAULT_BASE, document_at, resolve_base, working_tree_document,
)

LEDGER_PATH = f"gates/{LEDGER_FILE}"

# Re-exported so `tools.gates.ratchet` stays the one module a reader of the
# ledger's ratchet has to open. #204 moved the base-ref resolution to
# `tools/ratchets.py` when the SDK coverage manifest needed the same thing, and
# two copies of "which commit am I compared against?" is the arrangement that
# decides whether a gate compares against anything at all.
__all__ = ["Comparison", "DEFAULT_BASE", "LEDGER_PATH", "compare", "ledger_at",
           "resolve_base", "run"]


@dataclass(frozen=True)
class Comparison:
    """What changed between two ledgers, and what the rules say about it."""
    added: tuple
    removed: tuple
    deferred: tuple
    faults: tuple

    @property
    def ok(self):
        return not self.faults


def _index(document):
    """`{(gate, site): entry}` for a parsed ledger document.

    Deliberately tolerant: the base branch's ledger is *history*, and history
    that fails today's schema must not stop today's comparison from running.
    The head ledger's own validity is the compiler's job, and it has already
    run by the time anything here matters.
    """
    entries = {}
    for body in (document or {}).get("entries") or []:
        if not isinstance(body, dict):
            continue
        gate, site = body.get("gate"), body.get("site")
        if isinstance(gate, str) and isinstance(site, str):
            entries[(gate, site)] = body
    return entries


def _authorised_gates(document):
    """Which gates the document's seeding authorisations name, and for how many."""
    counts = {}
    for body in (document or {}).get("seeding_authorisations") or []:
        if not isinstance(body, dict):
            continue
        gate, added = body.get("gate"), body.get("entries_added")
        if isinstance(gate, str) and isinstance(added, int):
            counts[gate] = counts.get(gate, 0) + added
    return counts


def _authorisation_identities(document):
    """What makes one authorisation distinguishable from another.

    The gate and the issue: re-seeding the same gate from a later ticket is a
    new act needing a new authorisation, and must not be licensed by the entry
    that authorised the first one.
    """
    identities = set()
    for body in (document or {}).get("seeding_authorisations") or []:
        if isinstance(body, dict):
            identities.add((body.get("gate"), body.get("issue")))
    return identities


def _slice_order(slices, key):
    entry = slices.get(key)
    return entry.order if entry is not None else None


def compare(base_document, head_document, slices):
    """The verdict on ``head_document`` given the ledger at the base ref.

    Pure, over two parsed documents, so the negative controls put synthetic
    ledgers through the same entry point CI uses.
    """
    base, head = _index(base_document), _index(head_document)

    added = tuple(sorted(set(head) - set(base)))
    removed = tuple(sorted(set(base) - set(head)))

    new_authorisations = (_authorisation_identities(head_document)
                          - _authorisation_identities(base_document))
    licensed = {}
    for gate, issue in new_authorisations:
        for body in head_document.get("seeding_authorisations") or []:
            if (isinstance(body, dict) and body.get("gate") == gate
                    and body.get("issue") == issue
                    and isinstance(body.get("entries_added"), int)):
                licensed[gate] = licensed.get(gate, 0) + body["entries_added"]

    faults = []
    added_per_gate = {}
    for gate, site in added:
        added_per_gate[gate] = added_per_gate.get(gate, 0) + 1
    for gate, count in sorted(added_per_gate.items()):
        if gate not in licensed:
            sites = ", ".join(site for entry_gate, site in added
                              if entry_gate == gate)
            faults.append(GateError(
                codes.LEDGER_GREW, LEDGER_PATH,
                f"{count} entr{'y' if count == 1 else 'ies'} added for {gate} "
                f"with no seeding authorisation naming it in this change "
                f"({sites}). The ledger only shrinks: record the addition as a "
                f"reviewed act by adding a `seeding_authorisations` entry that "
                f"names the gate, the issue, how many entries it adds and why."))
        elif licensed[gate] != count:
            faults.append(GateError(
                codes.AUTHORISATION_COUNT_WRONG, LEDGER_PATH,
                f"the seeding authorisation for {gate} licenses "
                f"{licensed[gate]} entr{'y' if licensed[gate] == 1 else 'ies'}, "
                f"but {count} arrived. A reviewer approves a quantity, not an "
                f"intention."))
    for gate in sorted(set(licensed) - set(added_per_gate)):
        faults.append(GateError(
            codes.AUTHORISATION_INERT, LEDGER_PATH,
            f"the seeding authorisation for {gate} licenses "
            f"{licensed[gate]} entries and none arrived. An override that "
            f"overrides nothing is the shape of a check that cannot fail — "
            f"delete it, or add the entries it was written for."))

    deferred = []
    for identity in sorted(set(head) & set(base)):
        was = _slice_order(slices, base[identity].get("owner_slice"))
        now = _slice_order(slices, head[identity].get("owner_slice"))
        if was is None or now is None or now <= was:
            continue
        deferred.append(identity)
        faults.append(GateError(
            codes.DEBT_DEFERRED, f"{LEDGER_PATH}: {head[identity].get('id')}",
            f"the owner slice moved later, from "
            f"`{base[identity].get('owner_slice')}` to "
            f"`{head[identity].get('owner_slice')}`. Deferring a debt is not "
            f"shrinking the ledger; it is the failure #155 §17 recorded, with "
            f"an extra step. Moving one earlier is free."))

    return Comparison(added=added, removed=removed, deferred=tuple(deferred),
                      faults=tuple(faults))


# ---------------------------------------------------------------------------
# Reading the base ref
#
# `resolve_base` and the git plumbing live in `tools/ratchets.py`, shared with
# the SDK coverage ratchet. What stays here is the one thing that is about the
# LEDGER: which file to read.
# ---------------------------------------------------------------------------

def ledger_at(repo_root, ref):
    """The ledger document committed at ``ref``.

    A ref that never had the file returns an empty ledger rather than an error:
    that is the true state of a branch taken before this ticket landed, and
    every entry in the proposal is genuinely an addition.
    """
    return document_at(repo_root, ref, LEDGER_PATH)


def run(repo_root, slices, base=DEFAULT_BASE):
    """Resolve the base ref, read both ledgers, and compare. Returns a
    :class:`Comparison` whose ``faults`` are empty when the ratchet holds.

    The proposal is always the WORKING TREE's ledger, so an author gets the same
    verdict before committing that CI gives afterwards.
    """
    head_document = working_tree_document(repo_root, LEDGER_PATH)

    ref, problem = resolve_base(
        repo_root, base,
        proposal_is_committed=ledger_at(repo_root, "HEAD") == head_document)
    if problem is not None:
        return Comparison((), (), (), (GateError(codes.BASE_UNREADABLE,
                                                 LEDGER_PATH, problem),))

    base_document = ledger_at(repo_root, ref)
    if base_document is None:
        return Comparison((), (), (), (GateError(
            codes.BASE_UNREADABLE, LEDGER_PATH,
            f"the ledger at {ref} could not be read or parsed."),))
    return compare(base_document, head_document, slices)
