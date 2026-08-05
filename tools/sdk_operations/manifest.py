"""Render the coverage as the committed manifest, and compare it byte for byte.

ADR-0007 §4 requires the disposition of every published operation to live in "a
generated manifest that must stay mechanically accurate". This module is the
generated half — the same arrangement `tools/vocabulary/generate.py` gives the
backend constants, for the same reason: an artifact nobody may hand-edit, a
regeneration command, and a zero-diff gate that makes a stale copy impossible
to merge.

The file is written by hand rather than dumped with ``yaml.safe_dump``. Two
reasons, and neither is taste. It carries a banner and section comments a
dumper would drop, so the file explains itself to whoever opens it; and its
bytes are fixed by this module rather than by the installed PyYAML's emitter
settings, which is what a byte-comparison gate needs to be stable across
machines.
"""

from pathlib import Path

from tools.sdk_operations import errors as codes
from tools.sdk_operations.calls import SHELL_ROOT
from tools.sdk_operations.coverage import DISPOSITIONS
from tools.sdk_operations.errors import SurfaceError
from tools.sdk_operations.spec import SPEC_PATH

#: The committed manifest, relative to the git root.
MANIFEST_PATH = "ubb-sdk/operation-coverage.yaml"

_BANNER = (
    f"# @generated from {SPEC_PATH} and {SHELL_ROOT}/ — do not edit by hand.\n"
    "# Regenerate with `python -m tools.sdk_operations --write`.\n"
)

_PREAMBLE = f"""#
# Every operation the committed contract publishes, and what the SDK does about
# it (ADR-0007 §4, #155 §8.2). The count of unwrapped operations is NOT required
# to reach zero — the SDK is allowed deliberate gaps — but it must stay visible
# and mechanically accurate, and no operation may join them unsigned.
#
#   wrapped           a hand-written call in {SHELL_ROOT}/ resolves to it
#   generated_only    no hand-written call; the generated client has its module
#   not_yet_wrapped   no hand-written call and no generated module either —
#                     unreachable through this SDK by any route
#
# All three are DERIVED from the tree, never declared. A hand-written
# classification would be a second copy of a fact the repository already
# states, and the only question it could raise is whether the two copies agree.
#
# One consequence, flagged rather than buried: #155 §8.2 described
# `not_yet_wrapped` as "deliberately unavailable", imagining a human declaring
# it. Derived, it means "unreachable by any route" — a detector for an operation
# the pinned generator silently skipped, which G16 cannot see because it
# compares the generator against itself. Deliberateness moved to the
# authorisation; the word narrowed.
#
# `wrapped_by` names the declaring method rather than a line, so a call moving
# down its file is not a diff. Where one operation is reached from more than one
# place, every place is listed.
#
# The count is per OPERATION, not per path. #155 §1.3 counted 42 paths the SDK
# never calls; at the operation identity ADR-0007 §4 requires — method AND path
# — the same tree gives 56. Both numbers are right about different units.
"""

_SUMMARY_NOTE = """
# The lines a reviewer has to read. An operation JOINING the unwrapped set is
# refused by `python -m tools.sdk_operations ratchet` unless this change carries
# an entry in ubb-sdk/coverage-authorisations.yaml licensing exactly that many.
# The ratchet compares the set, not this total: wrapping three while publishing
# two unwrapped ones lowers the number and opens two gaps.
"""


def render(coverage):
    """The manifest's full text for this coverage."""
    counts = coverage.counts()
    lines = [_BANNER + _PREAMBLE, "version: 1", "",
             _SUMMARY_NOTE.strip("\n"),
             "summary:",
             f"  operations: {len(coverage.rows)}",
             f"  unwrapped: {coverage.unwrapped}"]
    lines += [f"  {disposition}: {counts[disposition]}"
              for disposition in DISPOSITIONS]
    lines.append("")
    lines.append("operations:")
    for row in coverage.rows:
        lines.append(f"  - operation_id: {row.operation_id}")
        lines.append(f"    method: {row.method}")
        lines.append(f"    path: {row.path}")
        lines.append(f"    disposition: {row.disposition}")
        if row.wrapped_by:
            lines.append("    wrapped_by:")
            lines += [f"      - {site}" for site in row.wrapped_by]
    return "\n".join(lines) + "\n"


def compare(coverage, repo_root):
    """``(fault or None, rendered bytes)`` for the committed manifest.

    The fault is ``None`` when the committed bytes are exactly what this
    coverage renders, and otherwise a
    :class:`~tools.sdk_operations.errors.SurfaceError` saying which way it is
    wrong. Missing and stale are separate codes because they are different
    faults with different fixes, and "no differences found" must never be what
    a deleted manifest looks like. The bytes come back either way so
    :func:`write` does not have to render twice.

    The comparison is over BYTES. Decoding would fold CRLF into LF and call a
    Windows working copy current, so this tool would report "up to date" about
    a file git reports as modified — the same call `tools/vocabulary` makes.
    """
    rendered = render(coverage).encode("utf-8")
    path = Path(repo_root) / MANIFEST_PATH
    if not path.is_file():
        return SurfaceError(
            codes.MANIFEST_MISSING, MANIFEST_PATH,
            "the coverage manifest is not committed. Run "
            "`python -m tools.sdk_operations --write`."), rendered
    if path.read_bytes() != rendered:
        return SurfaceError(
            codes.MANIFEST_DIFFERS, MANIFEST_PATH,
            "the committed manifest is not what the contract and the SDK "
            "produce. A published operation added, renamed or newly wrapped "
            "since it was last generated will show here: run "
            "`python -m tools.sdk_operations --write` and commit the result."
        ), rendered
    return None, rendered


def write(coverage, repo_root):
    """Regenerate the manifest if it is stale; return whether it was rewritten.

    Written as bytes, so the newlines are this renderer's LF on every platform
    rather than whatever the local text mode would substitute. A contributor on
    Windows regenerating a CRLF file would otherwise hand CI a diff nobody can
    see in a review.
    """
    stale, rendered = compare(coverage, repo_root)
    if stale is None:
        return False
    path = Path(repo_root) / MANIFEST_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(rendered)
    return True
