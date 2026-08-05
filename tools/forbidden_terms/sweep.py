"""The workhorse gate: no retired word on any living surface.

#154 §12 calls the forbidden-term sweep the workhorse and names its input — the
retirement table, which #198 and #202 made registry data rather than a list
somebody maintains by memory. This module is the walker over it.

**What it reads.** Every file `git ls-files` reports. Not a list of roots: a list
of roots is a thing that can quietly lose an entry, and the one surface nobody
checks is where the old word survives. Starting from the whole tree also deletes
a whole exclusion category — `.venv`, `node_modules`, `__pycache__` and build
output are not tracked, so no rule has to name them, and the declared exclusions
are exactly the *semantic* ones #154 §14 warned about.

**How it matches.** The retired token, exactly as the registry spells it, with a
non-identifier character required on each side. `\\b` will not do: it treats `_`
as a word character in the wrong direction for this job, and several retired
terms are dotted event names where the dot is part of the token.

**What it does not catch, stated rather than discovered.** The match is
case-sensitive and over the token as spelled, so a Pascal-cased spelling of a
retired word is not a hit — and it is not any other gate's subject either today.
Making it one means a normalised match, which would turn every single-word term
into its sentence-initial capitalisation throughout the living docs, or a second
declared list of spellings. Both are decisions, and neither is this ticket's;
what belongs here is that the gap is written down rather than discovered.

**And the sense-retired words are not input at all.** #202's `retired_senses`
carries the words retired in one sense while live in another, precisely so this
sweep never sees them. ADR-0008 §1 is the authority: a question needing
judgement about meaning is human-judged, not machine-gated.

Nothing in this package spells a live retired term, including in a comment. The
sweep reads it like any other first-party module, and a walker that had to be
excused from its own rule would be a poor advertisement for the rule.
"""

import re
from dataclasses import dataclass

from tools.forbidden_terms import errors as codes
from tools.forbidden_terms.errors import SweepError
from tools.ratchets import git

#: `found: N files` on a G7 ledger entry — the extent the entry excuses.
EXTENT = re.compile(r"^(\d+) files?$")


@dataclass(frozen=True)
class Occurrence:
    """One retired term, in one area, with the files it is in.

    The FILE list rather than a line count is deliberate, and it is what the
    ledger records. A line count changes when anyone edits a line, which would
    make every entry a moving number nobody could ratchet against. The file
    count changes when a retired word reaches somewhere it was not, which is the
    thing worth refusing while the debt stands.
    """
    term: str
    concept: str
    area: str
    files: tuple

    @property
    def extent(self):
        return len(self.files)


@dataclass(frozen=True)
class Result:
    swept: tuple
    excluded: dict
    occurrences: tuple
    faults: tuple

    @property
    def ok(self):
        return not self.faults

    def by_site(self):
        """``{(area, term): Occurrence}`` — keyed the way the ledger sites are."""
        return {(o.area, o.term): o for o in self.occurrences}

    def describe(self):
        """Human-readable report lines. Shared by the CLI and its test, so what
        a reader sees is what the test asserts on."""
        excluded = sum(len(paths) for paths in self.excluded.values())
        lines = [
            f"swept: {len(self.swept)} files",
            f"excluded: {excluded} files across {len(self.excluded)} declared "
            f"rule(s)",
        ]
        for rule_id in sorted(self.excluded):
            lines.append(f"  {rule_id}: {len(self.excluded[rule_id])}")
        lines.append(f"retired terms on a living surface: "
                     f"{len({o.term for o in self.occurrences})} "
                     f"in {len(self.occurrences)} (area, term) site(s)")
        return lines


def pattern(term):
    """The token, with a non-identifier character required on each side."""
    return re.compile(r"(?<![A-Za-z0-9_])" + re.escape(term)
                      + r"(?![A-Za-z0-9_])")


def tracked_files(repo_root):
    """Every path `git ls-files` reports, POSIX and sorted.

    Returns ``(paths, problem)``. A tree that cannot be listed is a FAULT, never
    an empty sweep: "found no retired words" and "read no files" are the same
    output, and the second one is how a gate goes green by doing nothing.
    """
    completed = git(repo_root, "ls-files", "-z")
    if completed.returncode != 0:
        return (), SweepError(
            codes.TREE_UNREADABLE, ".",
            f"`git ls-files` failed ({completed.returncode}): "
            f"{completed.stderr.strip()}. The sweep reads the tracked tree, and "
            f"a sweep that cannot list it must fail rather than report nothing.")
    paths = tuple(sorted(p for p in completed.stdout.split("\0") if p))
    if not paths:
        return (), SweepError(
            codes.TREE_UNREADABLE, ".",
            "`git ls-files` reported no files at all")
    return paths, None


def partition(paths, plan):
    """Split the tree into what is swept and what each rule excludes.

    This is the accounting, and it is total: every path lands in exactly one
    place or a fault says why not.
    """
    swept = []
    excluded = {rule.id: [] for rule in plan.exclusions}
    faults = []
    for path in paths:
        matched = [rule.id for rule in plan.exclusions if rule.matches(path)]
        if not matched:
            swept.append(path)
            continue
        if len(matched) > 1:
            faults.append(SweepError(
                codes.RULE_OVERLAP, path,
                f"excused by {len(matched)} rules at once "
                f"({', '.join(matched)}). Each excluded file belongs to exactly "
                f"one rule, or the per-rule counts stop meaning anything and "
                f"deleting one rule silently changes another's."))
        excluded[matched[0]].append(path)
    return tuple(swept), {k: tuple(v) for k, v in excluded.items()}, tuple(faults)


def accounting_faults(plan, excluded):
    """Everything the exclusion list claims about itself, checked.

    The counts are the anti-widening mechanism and the anchors are the
    anti-disarming one, and they fail differently on purpose: a count says the
    blind spot changed size, an anchor says the sweep stopped reading somewhere
    it must.
    """
    faults = []
    for rule in plan.exclusions:
        actual = len(excluded.get(rule.id, ()))
        where = f"gates/forbidden-term-sweep.yaml: {rule.id}"
        if actual == 0:
            faults.append(SweepError(
                codes.RULE_INERT, where,
                "this rule excludes nothing. An exclusion that excludes nothing "
                "is the same shape as a check that cannot fail — delete it, or "
                "correct the paths it was written for."))
        elif actual != rule.files:
            direction = "more" if actual > rule.files else "fewer"
            faults.append(SweepError(
                codes.RULE_COUNT_WRONG, where,
                f"declares {rule.files} file(s) and excludes {actual} — "
                f"{direction} than declared. The count is the whole anti-"
                f"widening mechanism: if the exclusion genuinely covers "
                f"{actual} now, say {actual} here, in a diff a reviewer sees."))
    for anchor in plan.anchors:
        for rule in plan.exclusions:
            if rule.matches(anchor):
                faults.append(SweepError(
                    codes.RULE_HIDES_ANCHOR, f"{rule.id}: {anchor}",
                    f"`{anchor}` is an anchor — a file this sweep must be shown "
                    f"to have read — and this rule excludes it. An exclusion "
                    f"that covers an anchor has widened over a living surface."))
    return tuple(faults)


def vacuity_faults(plan, swept):
    """Proof the sweep read the surfaces it claims to.

    #191 story 20: a path-resolution bug must not turn a gate into a test that
    always passes. Two claims, because one is not enough — every declared anchor
    was read, AND every area has one. The second is what stops a new area from
    arriving unguarded, which is how the first would rot.
    """
    read = set(swept)
    faults = [
        SweepError(codes.ANCHOR_MISSING, anchor,
                   "a declared anchor was not among the files swept. The sweep "
                   "did not read a surface it claims to cover.")
        for anchor in plan.anchors if anchor not in read
    ]
    anchored = {plan.area_of(anchor) for anchor in plan.anchors}
    for area in plan.area_names:
        if area not in anchored:
            faults.append(SweepError(
                codes.AREA_UNANCHORED, area,
                f"no anchor resolves to the `{area}` area, so nothing proves "
                f"the sweep read it. Every area carries at least one."))
    return tuple(faults)


def run(repo_root, registry, plan, paths=None):
    """Sweep the tracked tree for the registry's retired terms.

    ``paths`` overrides the tracked-file listing, which is how the negative
    controls drive the real walker over a synthetic tree without a git
    repository in a temporary directory.
    """
    faults = []
    if paths is None:
        paths, problem = tracked_files(repo_root)
        if problem is not None:
            return Result((), {}, (), (problem,))

    swept, excluded, partition_faults = partition(paths, plan)
    faults.extend(partition_faults)
    faults.extend(accounting_faults(plan, excluded))
    faults.extend(vacuity_faults(plan, swept))

    terms = registry.retired_terms
    patterns = {term: pattern(term) for term in terms}
    found = {}
    for path in swept:
        try:
            text = (repo_root / path).read_text(encoding="utf-8")
        except UnicodeDecodeError:
            faults.append(SweepError(
                codes.FILE_UNDECODABLE, path,
                "a swept file is not valid UTF-8. It is not skipped: a file the "
                "sweep cannot read is a file a retired word can hide in, so it "
                "is either declared in an exclusion rule or it is a fault."))
            continue
        except FileNotFoundError:
            faults.append(SweepError(
                codes.TREE_UNREADABLE, path,
                "`git ls-files` reports this file and it is not on disk. The "
                "sweep is reading a tree that is mid-change, so its verdict "
                "would be about neither state."))
            continue
        except OSError as problem:
            faults.append(SweepError(codes.FILE_UNDECODABLE, path, str(problem)))
            continue
        area = plan.area_of(path)
        for term, matcher in patterns.items():
            if matcher.search(text):
                found.setdefault((area, term), []).append(path)

    occurrences = tuple(sorted(
        (Occurrence(term=term, concept=terms[term], area=area,
                    files=tuple(sorted(files)))
         for (area, term), files in found.items()),
        key=lambda o: (o.area, o.term)))
    return Result(swept=swept, excluded=excluded, occurrences=occurrences,
                  faults=tuple(faults))


# ---------------------------------------------------------------------------
# The gate: what the sweep found, against what the ledger excuses
# ---------------------------------------------------------------------------

def excused(entries):
    """``{(area, term): extent}`` from the G7 migration-ledger entries.

    ``site`` is ``<area>::<term>`` and ``found`` is ``N files``. Returns
    ``(extents, faults)`` — a `found` that will not parse is a fault rather than
    an unbounded excuse, because an entry whose extent nobody can read excuses
    any amount of spread.
    """
    extents, faults = {}, []
    for entry in entries:
        where = f"gates/migration-ledger.yaml: {entry.id}"
        area, _, term = entry.site.partition("::")
        if not area or not term:
            faults.append(SweepError(
                codes.LEDGER_EXTENT_UNPARSED, where,
                f"the site `{entry.site}` is not `<area>::<term>`"))
            continue
        match = EXTENT.match((entry.found or "").strip())
        if match is None:
            faults.append(SweepError(
                codes.LEDGER_EXTENT_UNPARSED, where,
                f"`found: {entry.found}` is not `N files`. A G7 entry records "
                f"the extent it excuses, so that a retired word reaching a file "
                f"it was not in fails while the debt still stands."))
            continue
        extents[(area, term)] = int(match.group(1))
    return extents, tuple(faults)


def gate_faults(result, extents):
    """The verdict: every excuse EXACTLY true, and every excuse still owed.

    The extent is checked in both directions, and the second one is not
    pedantry. An excuse that may overstate is an unbounded excuse — recording
    `999 files` against a term would licence any amount of spread, and nothing
    else in this mechanism would notice, because the ledger's ratchet compares
    entry identities rather than their contents. Requiring the number to be
    exactly true removes the question: the ledger cannot say anything about the
    tree that is not so.

    What it costs is an edit when a debt is partly paid, which is the change
    being recorded rather than an inconvenience — and the ratchet lets a number
    fall for free.
    """
    faults = []
    found = result.by_site()
    for site, occurrence in sorted(found.items()):
        area, term = site
        where = f"{area}::{term}"
        if site not in extents:
            faults.append(SweepError(
                codes.TERM_ON_LIVING_SURFACE, where,
                f"the retired term `{term}` appears on the `{area}` surface in "
                f"{occurrence.extent} file(s) and no ledger entry owes it. "
                f"`{occurrence.concept}` is what replaced it "
                f"(first: {occurrence.files[0]})."))
        elif occurrence.extent > extents[site]:
            faults.append(SweepError(
                codes.TERM_SPREAD, where,
                f"the retired term `{term}` is in {occurrence.extent} file(s) "
                f"on the `{area}` surface; its ledger entry records "
                f"{extents[site]}. The debt is a finite migration plan, not a "
                f"licence for the word to reach further while it stands."))
        elif occurrence.extent < extents[site]:
            faults.append(SweepError(
                codes.LEDGER_EXTENT_OVERSTATED, where,
                f"the retired term `{term}` is in {occurrence.extent} file(s) "
                f"on the `{area}` surface; its ledger entry records "
                f"{extents[site]}. Part of this debt is paid — record it as "
                f"`found: {occurrence.extent} files`. An entry that may "
                f"overstate is an excuse with no upper bound."))
    for site in sorted(set(extents) - set(found)):
        area, term = site
        faults.append(SweepError(
            codes.LEDGER_ENTRY_STALE, f"{area}::{term}",
            f"a ledger entry owes `{term}` on the `{area}` surface and the "
            f"sweep finds it nowhere there. Paying a debt and deleting its "
            f"entry are one act — an entry cannot outlive the debt it records."))
    return tuple(faults)
