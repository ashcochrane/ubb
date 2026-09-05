"""An ADR that names its proof names one that exists (#374).

The ratchet asks for a rule in an ADR to be **backed by a test**, on the
product-boundaries ADR's precedent, because *a rule in prose that nothing
type-checks is a rule that drifts*. Slice 4's two ADRs answer that with a
``## What proves it`` section naming the module and the case behind each rule.

**Which creates the defect it was meant to cure, one level up.** A table of
twenty test names in a Markdown file is exactly the cross-reference this
repository already warns about at ``apps/metering/queries.py`` — *a path quoted
in prose is a cross-reference nothing type-checks* — and a renamed class leaves
the ADR quietly claiming a proof that no longer exists. Nothing else in the tree
would notice: the suites stay green, because the test is still there under its
new name, and only a reader following the citation finds out.

So this is the walker over that section. Two claims, and the second is the one
worth having:

1. **Every module an ADR names exists**, at the path it names, relative to the
   git root.
2. **Every case an ADR names is defined in a module the SAME ADR names.** Not
   "exists somewhere in the tree": an ADR that cites a class without saying
   which module holds it has not given a reader anything to follow, and an ADR
   whose class moved to another module has a stale table even though the class
   is alive.

⚠ **WHAT RULE 2 DOES NOT CHECK, STATED RATHER THAN DISCOVERED.** It binds a case
to a MODULE, not to the class cited beside it. A row reading *``SomeTest`` —
``test_a_thing``* stays green if `test_a_thing` moves to a sibling class in the
same file, so the pairing a reader sees is not enforced. That is deliberate
rather than missed: **the rows legitimately cross classes.** ADR-0009's §1 row
names `test_no_row_is_reopened_and_the_database_is_what_refuses_it` — a method of
`ACancellationIsAFurtherPublishTest` — alongside
`TheDatabaseRefusesTheEarlierCaseRegardlessTest`, because one rule is proved from
two places. A per-row class binding would report that honest row as a defect, so
the tighter rule is the wrong rule here, and the looser one is written down.

**THE SECTION HEADING IS THE OPT-IN, WHICH IS WHY THIS DOES NOT SWEEP EVERY
ADR.** The older ADRs cite their evidence in prose of several shapes, and a
walker that tried to parse all of them would either be a pile of special cases
or would quietly match nothing in most files. An ADR adopting the heading is
adopting the check; :func:`test_the_adrs_that_opted_in_are_the_ones_expected`
is what stops that opt-in being silently lost.

**Read by AST, never imported.** This suite runs without Django
(``test_contract_suite_is_enforced.py`` makes that a rule), and the modules
named here are platform tests that import models and settings. Reading their
definitions is a parse, not an import — and it is also the honest question,
because what the ADR cites is a *name in a file*.

⚠ **THE READER IS SHARED WITH THE CONTROLS BY CONSTRUCTION.** Every negative
control below drives :func:`findings` over a synthetic ADR, so a bug in the
parser reddens the controls rather than hiding behind a second copy of the
search. That is the shape #373 paid for: a positive control that re-implemented
the walk it was checking found nothing wrong with a walk that was wrong.
"""

import ast
import re
from pathlib import Path

import pytest

from _helpers import REPO_ROOT

#: BOTH ADR HOMES, BECAUSE `CLAUDE.md` NAMES TWO. New, sequential ADRs live in
#: `docs/adr/`; the pre-existing ones — including the product-boundaries ADR
#: whose precedent this check's own rationale rests on — live in
#: `docs/architecture/`. Globbing only the first would leave a
#: `## What proves it` added to the second silently unchecked, and the opt-in
#: guard would not notice either, because it reads the same listing.
ADR_DIRECTORIES = (REPO_ROOT / "docs" / "adr",
                   REPO_ROOT / "docs" / "architecture")

#: The heading that opts an ADR into this check.
PROOF_HEADING = "## What proves it"

#: Backticked spans, which is how this repository writes every symbol and path.
BACKTICKED = re.compile(r"`([^`\n]+)`")

#: A module the ADR names: a git-root-relative path to a Python file.
MODULE = re.compile(r"^[\w./-]+\.py$")

#: A case the ADR names — `unittest`'s class suffix, or a pytest function.
CASE = re.compile(r"^(?:[A-Z][A-Za-z0-9]*Test|test_[a-z0-9_]+)$")

#: The ADRs carrying the section today. A LIST RATHER THAN A COUNT, because the
#: failure this guards against is the heading being renamed or dropped — and a
#: count would go on passing if one ADR lost it while another gained one.
OPTED_IN = (
    "0009-a-correction-is-a-further-publish.md",
    "0010-recovery-projects-stripe-moves-the-money.md",
    "0011-a-unit-of-work-is-a-kernel-concept-at-the-root.md",
    "0012-how-a-kind-of-work-is-sold-is-frozen.md",
    "0013-a-delivered-unit-of-work-is-charged-once-by-a-charge-that-projects-onto-one-posting.md",
)


def proof_section(text):
    """The ``## What proves it`` section, or ``None`` if the ADR has none.

    Ends at the next second-level heading, so the Consequences below it are not
    scanned — a consequence may name a symbol it is not claiming as proof.
    """
    start = text.find(PROOF_HEADING)
    if start == -1:
        return None
    rest = text[start + len(PROOF_HEADING):]
    end = rest.find("\n## ")
    return rest if end == -1 else rest[:end]


def cited(section):
    """``(modules, cases)`` — the paths and the case names the section names."""
    modules, cases = [], []
    for span in BACKTICKED.findall(section):
        if MODULE.match(span):
            modules.append(span)
        elif CASE.match(span):
            cases.append(span)
    return tuple(dict.fromkeys(modules)), tuple(dict.fromkeys(cases))


def defined_in(path):
    """Every class and function name defined anywhere in one module.

    Methods included: a `unittest` case is a method on its class, and the ADR
    cites it by its own name because that is how it is run and reported.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {node.name for node in ast.walk(tree)
            if isinstance(node, (ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef))}


def findings(adr_name, text):
    """Everything wrong with one ADR's proof section, as readable lines.

    Returns ``[]`` for an ADR with no such section — having one is opt-in, and
    :func:`test_the_adrs_that_opted_in_are_the_ones_expected` is what holds the
    opt-in list honest rather than this function.
    """
    section = proof_section(text)
    if section is None:
        return []
    modules, cases = cited(section)
    problems = []

    if cases and not modules:
        problems.append(
            f"{adr_name}: names {len(cases)} case(s) and no module. A case "
            f"without the module holding it is not something a reader can "
            f"follow, and nothing can check it.")

    present = {}
    for module in modules:
        path = REPO_ROOT / module
        if not path.is_file():
            problems.append(
                f"{adr_name}: names `{module}`, which is not a file. A proof "
                f"table citing a path that does not resolve is the drift this "
                f"check exists for.")
            continue
        present[module] = defined_in(path)

    everywhere = set().union(*present.values()) if present else set()
    for case in cases:
        if case not in everywhere:
            problems.append(
                f"{adr_name}: names `{case}`, which none of the "
                f"{len(present)} module(s) it cites defines. Either the case "
                f"was renamed and the ADR was not, or it lives in a module "
                f"this ADR does not name.")
    return problems


def adrs():
    """``{filename: text}`` for every ADR in either home."""
    return {path.name: path.read_text(encoding="utf-8")
            for directory in ADR_DIRECTORIES
            for path in sorted(directory.glob("*.md"))}


# ---------------------------------------------------------------------------
# The shipped ADRs
# ---------------------------------------------------------------------------

def test_every_proof_an_adr_names_resolves():
    """The rule itself, over every ADR that opted in."""
    problems = [line
                for name, text in adrs().items()
                for line in findings(name, text)]

    assert problems == [], "\n".join(problems)


def test_the_adrs_that_opted_in_are_the_ones_expected():
    """The vacuity guard, and it is the load-bearing half.

    A heading renamed in both ADRs, or a `find` that stopped matching, would
    leave the rule above passing over nothing at all — the failure shape this
    repository has shipped more than once. Naming the files means losing the
    section is a red test rather than a silent green one.
    """
    opted_in = tuple(name for name, text in adrs().items()
                     if proof_section(text) is not None)

    assert opted_in == OPTED_IN


def test_the_opted_in_adrs_actually_cite_something():
    """And that each one's section is not an empty table.

    A section present but citing nothing would satisfy the guard above while
    proving no rule at all.
    """
    thin = []
    for name in OPTED_IN:
        modules, cases = cited(proof_section(adrs()[name]))
        if not modules or not cases:
            thin.append(f"{name}: {len(modules)} module(s), {len(cases)} case(s)")

    assert thin == [], "\n".join(thin)


# ---------------------------------------------------------------------------
# The negative controls — the same reader, over a synthetic ADR
# ---------------------------------------------------------------------------

REAL_MODULE = ("ubb-platform/apps/metering/pricing/tests/"
               "test_what_a_recovery_would_be_worth.py")
REAL_CASE = "NoneOfTheThreeMovesMoneyTest"


def an_adr(body):
    return f"# ADR-9999: synthetic\n\n{PROOF_HEADING}\n\n{body}\n"


def test_the_reader_accepts_a_citation_that_does_resolve():
    """The positive control. Without it every refusal below could be a parser
    that finds nothing and calls it clean."""
    text = an_adr(f"| a rule | `{REAL_MODULE}` — `{REAL_CASE}` |")

    assert findings("synthetic.md", text) == []


def test_a_module_that_does_not_exist_is_a_finding():
    text = an_adr("| a rule | `ubb-platform/apps/nowhere/test_nothing.py` |")

    (problem,) = findings("synthetic.md", text)
    assert "not a file" in problem


def test_a_case_no_cited_module_defines_is_a_finding():
    text = an_adr(f"| a rule | `{REAL_MODULE}` — `TheCaseThatNeverWasTest` |")

    (problem,) = findings("synthetic.md", text)
    assert "TheCaseThatNeverWasTest" in problem


def test_a_case_that_exists_in_another_module_is_still_a_finding():
    """The claim that makes rule 2 worth more than "it exists somewhere".

    `ACancellationIsAFurtherPublishTest` is a real class in a real module — just
    not in the one this synthetic ADR names.
    """
    text = an_adr(f"| a rule | `{REAL_MODULE}` — `ACancellationIsAFurtherPublishTest` |")

    (problem,) = findings("synthetic.md", text)
    assert "ACancellationIsAFurtherPublishTest" in problem
    assert "does not name" in problem


def test_a_section_naming_cases_and_no_module_is_a_finding():
    text = an_adr(f"| a rule | `{REAL_CASE}` |")

    problems = findings("synthetic.md", text)
    assert any("no module" in problem for problem in problems)


def test_an_adr_with_no_such_section_is_not_examined():
    """Opt-in, stated as behaviour rather than as an omission."""
    assert findings("synthetic.md", "# ADR-9999\n\n## Decision\n\n`Nope`\n") == []


def test_the_consequences_below_the_section_are_not_scanned():
    """The section ends at the next heading, and that boundary is real.

    A consequence may name a symbol without claiming it as proof, and scanning
    it would make the check refuse honest prose.
    """
    text = (an_adr(f"| a rule | `{REAL_MODULE}` — `{REAL_CASE}` |")
            + "\n## Consequences\n\n- `SomeClassThatIsNotATest`, "
              "and `test_a_case_that_does_not_exist_anywhere`\n")

    assert findings("synthetic.md", text) == []


@pytest.mark.parametrize("span,is_module", [
    ("ubb-platform/core/tests/test_scheduling.py", True),
    ("valid_to", False),
    ("PROJECTED_ADJUSTMENT_BASIS", False),
    ("uq_rate_active_in_pricing_book", False),
])
def test_only_a_python_path_is_read_as_a_module(span, is_module):
    """A section carries backticked prose too, and it must pass through.

    ⚠ `uq_rate_active_in_pricing_book` is the case worth pinning: it starts with
    no `test_` and ends with no `Test`, so it is neither — but a looser rule
    would have read it as a case and demanded a definition for a database
    constraint.
    """
    modules, cases = cited(f"`{span}`")

    assert bool(modules) is is_module
    assert cases == ()


# ---------------------------------------------------------------------------
# An ADR that departs from a frozen decision names the document it departs
# from (#426)
# ---------------------------------------------------------------------------
#
# `CLAUDE.md`'s ratchet says that when a slice departs from a decision a frozen
# document made, the ADR recording the departure names the document and the
# section it supersedes, quotes what that section said, and states the
# evidence. The quoting and the evidence are review's to judge. The NAMING is
# checkable, and it is the half that decays silently: a header reading
# *Supersedes: #141 §3* is a cross-reference nothing type-checks, and a reader
# who does not know which dated file resolves #141 is left to guess.
#
# The rule: a departure line in an ADR's header (`Supersedes`, `Amends`,
# `Reverses`) that names an issue-numbered decision must be accompanied, in the
# same header, by the backticked path of the frozen document under
# `docs/plans/` whose `**Resolves:**` line carries that issue — where such a
# document exists. Departures from another ADR, or from a document that says
# which issue it resolves nowhere, are outside the rule and are said to be.

#: A header field that records a departure from an earlier decision.
DEPARTURE_FIELD = re.compile(r"^-?\s*\*\*(Supersedes|Amends|Reverses):\*\*")

#: Any header field, which is where one departure field ends and the next
#: field begins — a field wraps onto continuation lines.
HEADER_FIELD = re.compile(r"^-?\s*\*\*[A-Za-z ]+:\*\*")

#: An issue-numbered decision named on a departure field.
ISSUE_NUMBER = re.compile(r"#(\d+)\b")

#: The frozen documents this repository writes decisions in.
FROZEN_DOCUMENT = re.compile(r"`(docs/plans/[\w./-]+\.md)`")

#: How a frozen decision document says which issue it resolves.
RESOLVES = re.compile(r"^\*\*Resolves:\*\*\s*\[#(\d+)\]", re.MULTILINE)

#: The ADRs whose departure fields name an issue-numbered decision today. A
#: LIST RATHER THAN A COUNT, for the reason `OPTED_IN` is one: a header
#: reworded so the field no longer matches would otherwise leave the rule
#: passing over fewer files with nothing red.
DEPARTING = (
    "0008-audit-method-and-launch-gates.md",
    "0009-a-correction-is-a-further-publish.md",
    "0011-a-unit-of-work-is-a-kernel-concept-at-the-root.md",
)


def header_of(text):
    """Everything above an ADR's first second-level heading."""
    end = text.find("\n## ")
    return text if end == -1 else text[:end]


def departure_issues(header):
    """The issue numbers named on the header's departure fields, with their
    continuation lines — a field wraps, and the number is often on the
    second line."""
    issues, inside = set(), False
    for line in header.splitlines():
        if HEADER_FIELD.match(line):
            inside = bool(DEPARTURE_FIELD.match(line))
        if inside:
            issues.update(int(n) for n in ISSUE_NUMBER.findall(line))
    return issues


def frozen_decisions():
    """``{issue number: git-root-relative path}`` for every dated decision
    under `docs/plans/` that says which issue it resolves."""
    decisions = {}
    for path in sorted((REPO_ROOT / "docs" / "plans").glob("*.md")):
        found = RESOLVES.search(path.read_text(encoding="utf-8"))
        if found:
            decisions[int(found.group(1))] = path.relative_to(REPO_ROOT).as_posix()
    return decisions


def departure_findings(adr_name, text, decisions):
    """Everything wrong with one ADR's departure fields, as readable lines,
    and whether the ADR has any such field to judge."""
    header = header_of(text)
    issues = departure_issues(header)
    named = set(FROZEN_DOCUMENT.findall(header))
    problems = []
    for issue in sorted(issues):
        document = decisions.get(issue)
        if document is not None and document not in named:
            problems.append(
                f"{adr_name}: departs from #{issue} and its header does not "
                f"name `{document}`, the frozen document that resolves it.")
    return problems, bool(issues)


def test_an_adr_that_departs_from_a_frozen_decision_names_the_document():
    """The rule itself, over every ADR in both homes."""
    decisions = frozen_decisions()
    assert decisions, "no dated decision under docs/plans says what it resolves"
    problems = [line
                for name, text in adrs().items()
                for line in departure_findings(name, text, decisions)[0]]

    assert problems == [], "\n".join(problems)


def test_the_adrs_that_depart_are_the_ones_expected():
    """The vacuity guard: the ADRs the rule actually examined."""
    departing = tuple(name for name, text in adrs().items()
                      if departure_findings(name, text, frozen_decisions())[1])

    assert departing == DEPARTING


def test_a_departure_that_names_no_frozen_document_is_a_finding():
    """The negative control, over a synthetic header against the real
    decisions, so the parser proves itself on a case that must fail."""
    text = ("# ADR-9999: synthetic\n\n**Status:** accepted\n"
            "**Supersedes:** #141 §3's table row\n\n## Context\n")

    problems, examined = departure_findings("synthetic.md", text,
                                            frozen_decisions())
    assert examined
    (problem,) = problems
    assert "#141" in problem
    assert "2026-07-30-task-lifecycle-placement-decision.md" in problem


def test_a_departure_that_names_the_document_is_clean():
    """The positive control, and the wrapped-field case in one: the issue
    number sits on the field's second line."""
    text = ("# ADR-9999: synthetic\n\n"
            "**Decision records:** "
            "`docs/plans/2026-07-30-task-lifecycle-placement-decision.md`\n"
            "**Supersedes:** the registry row in\n"
            "#141 §3, and nothing else\n\n## Context\n")

    problems, examined = departure_findings("synthetic.md", text,
                                            frozen_decisions())
    assert examined
    assert problems == []


def test_a_departure_from_another_adr_is_outside_the_rule():
    """ADR-0006 supersedes ADR-0005: no issue number, nothing to resolve."""
    text = ("# ADR-9999: synthetic\n\n**Supersedes:** ADR-0005 on its central "
            "noun\n\n## Context\n")

    problems, examined = departure_findings("synthetic.md", text,
                                            frozen_decisions())
    assert not examined
    assert problems == []
