"""The guarantees document's pin ledger names tests that exist (#470).

`docs/spend-control-guarantees.md` §9 is a table of twenty-nine promises, each
citing the test that holds it, under a heading that invites the reader to *"run
any row yourself"*. That is the same cross-reference
`tests/contracts/test_adr_proof_tables.py` exists to guard one level up — *a
path quoted in prose is a cross-reference nothing type-checks* — and this
document had drifted exactly as that module predicts: when #470 opened it,
**three citations named things the tree no longer had** (a class renamed
`Pin3BelowFloorLandsTest` → `Pin3WalletNoFloorCheckTest`, and a module renamed
`test_live_ledger.py` → `test_live_counter.py`, cited twice). Every suite was
green the whole time, because each test was still there under its new name.
Only a reader following the citation would have found out, and the document's
whole purpose is to be followed by a skeptical reader.

So this is the walker over that section. Two claims:

1. **Every module §9 names exists**, at the path it names, relative to the git
   root.
2. **Every case §9 names is defined in a module the SAME section names.**

⚠ **THE SCOPE IS §9 AND NOTHING ELSE, DELIBERATELY.** §4's "pinned by tests"
table abbreviates its paths under a convention it states in its own prose
(*"All pointers are to `ubb-platform/`"*), so the spans there are not git-root
paths and would either need a prefix table here or a rewrite there. §9 is the
section that promises a runnable citation, so §9 is the section held to one.
That leaves §4 unchecked, which is written down rather than discovered.

⚠ **WHAT CLAIM 2 DOES NOT CHECK.** It binds a case to the SECTION's modules,
not to the path written beside it, and not to the class written beside it — the
same looseness `test_adr_proof_tables` documents, for the same reason: rows
here legitimately cite a method of one class beside a class of another module
(pin 3 names the constraint pin and, separately, the landing pin that lives in
billing's suite). A per-row binding would report those honest rows as defects.

**WHAT THIS MODULE OWNS IS THE CITATION SHAPE, AND ONLY THAT.** An ADR writes
its module and its case as two separate backticked spans; this table joins them
with `::` and continues a run of rows with a leading `::method`. So the span is
split here and each part classified. Reading a section out of a document,
reading the names a module defines, and deciding which citations fail to
resolve are all in `_helpers`, shared with the ADR walker — two copies of one
read are how the two come to disagree while both suites stay green.

⚠ **AND THE CASE PATTERN IS WIDER THAN THE ADR WALKER'S.** That one matches
`...Test` classes and `test_` functions only, so a pytest-style `TestFoo` class
named alone is silently unchecked — the go-narrow shape its own carry-forward
warns about. This table is full of them (`TestPin4DurableLane`,
`TestStopFlag`), so they are matched here and would redden on a rename.
"""

import re

from _helpers import REPO_ROOT, section_under, unresolved

#: The document this holds, and the heading that opens the section.
GUARANTEES = "docs/spend-control-guarantees.md"
PIN_HEADING = "## 9. The pin ledger"

#: Backticked spans, which is how this repository writes every symbol and path.
BACKTICKED = re.compile(r"`([^`\n]+)`")

#: What joins a path to a class to a method inside one span.
JOINER = "::"

#: A module §9 names: a git-root-relative path under `ubb-platform/`. The
#: prefix is REQUIRED rather than optional — an abbreviated path is the thing
#: that went stale unnoticed, so a row that drops it fails to resolve here
#: rather than being quietly accepted.
MODULE = re.compile(r"^ubb-platform/[\w./-]+\.py$")

#: A case §9 names: a `unittest` class, a pytest-style class, or a test
#: function. See the module docstring on why the middle one is here.
CASE = re.compile(r"^(?:[A-Z][A-Za-z0-9]*Test"
                  r"|Test[A-Z][A-Za-z0-9]*"
                  r"|test_[a-z0-9_]+)$")

#: The floor under the vacuity guard. Twenty-nine pins cite far more than this
#: between them; the number is a floor on "the section was found and parsed",
#: not a count of anything, so it does not move when a row gains a case.
FEWEST_CASES = 25


def pin_section(text):
    """The pin-ledger section, or ``None`` if the heading is gone.

    §9 is the last section of the document, so the closing note below it is
    included; it cites nothing.
    """
    return section_under(text, PIN_HEADING)


def cited(section):
    """``(modules, cases)`` — the paths and the case names the section names.

    A span is split on ``::`` and each part classified, so
    ``path::Class::method`` contributes one module and two cases, and a
    continuation ``::method`` contributes one case. A part matching neither
    pattern is ignored: rows also backtick field names, wire values and
    ordinary prose symbols, and this walker is not the judge of those.
    """
    modules, cases = [], []
    for span in BACKTICKED.findall(section):
        for part in span.split(JOINER):
            part = part.strip()
            if MODULE.match(part):
                modules.append(part)
            elif CASE.match(part):
                cases.append(part)
    return tuple(dict.fromkeys(modules)), tuple(dict.fromkeys(cases))


def findings(section):
    """Everything wrong with the pin ledger, as readable lines."""
    missing_modules, resolved, missing_cases = unresolved(*cited(section))
    problems = []

    for module in missing_modules:
        problems.append(
            f"§9 names `{module}`, which is not a file. A pin ledger citing "
            f"a path that does not resolve is the drift this check exists "
            f"for — and a reader told to run the row cannot.")
    for case in missing_cases:
        problems.append(
            f"§9 names `{case}`, which none of the {resolved} "
            f"module(s) it cites defines. Either the case was renamed and "
            f"the ledger was not, or it lives in a module §9 does not "
            f"name.")
    return problems


def guarantees():
    return (REPO_ROOT / GUARANTEES).read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# The shipped document
# ---------------------------------------------------------------------------

def test_every_pin_names_a_test_that_exists():
    """The rule itself."""
    section = pin_section(guarantees())
    assert section is not None, (
        f"{GUARANTEES} has no `{PIN_HEADING}` section. Either it was renamed "
        f"— in which case rename it here too — or the pin ledger was dropped, "
        f"in which case this check has silently stopped holding anything.")

    problems = findings(section)

    assert problems == [], "\n".join(problems)


def test_the_pin_ledger_is_not_an_empty_table():
    """The vacuity guard, and it is the load-bearing half.

    A heading renamed, a table emptied, or a `find` that stopped matching
    would leave the rule above passing over nothing at all — the failure shape
    this repository has shipped more than once.
    """
    modules, cases = cited(pin_section(guarantees()))

    assert len(cases) >= FEWEST_CASES, (
        f"§9 cites {len(cases)} case(s) across {len(modules)} module(s), "
        f"under the floor of {FEWEST_CASES}. The section parsed, so the rule "
        f"above is passing — over almost nothing.")


def abbreviated(section):
    """Every `.py` span in one section that is a path and does not resolve.

    A span is a PATH when it carries a directory separator; a bare filename is
    prose naming a module (*"read only through `flags.py`"*) and is left
    alone, because holding that to a git-root path would be holding a sentence
    to a citation's standard. What is left is the shape that rotted: a real
    directory path missing the root it is relative to.
    """
    return [part
            for span in BACKTICKED.findall(section)
            for part in [span.split(JOINER)[0].strip()]
            if part.endswith(".py") and "/" in part
            and not (REPO_ROOT / part).is_file()]


def test_no_row_abbreviates_the_path_it_cites():
    """And so no row quietly reverts to the convention that rotted.

    §9 used to say *"paths under `ubb-platform/`, abbreviated after first
    use"*. Under that convention a citation is not runnable without
    reconstructing a prefix, and three of them went stale while every suite
    stayed green. A directory path that resolves from nowhere is that
    convention coming back — and it would slip past the rule above too, which
    only reaches spans it recognises as modules.
    """
    loose = abbreviated(pin_section(guarantees()))

    assert loose == [], (
        "§9 cites these paths relative to nothing, so they cannot be pasted "
        "into pytest and are not checked above: " + ", ".join(loose))


# ---------------------------------------------------------------------------
# The negative controls — the same reader, over a synthetic section
# ---------------------------------------------------------------------------

REAL_MODULE = "ubb-platform/api/v1/tests/test_one_rule_pins.py"
REAL_CLASS = "Pin7TwoHundredAlwaysTest"
REAL_METHOD = "test_no_usage_report_path_answers_429_or_409"


def a_ledger(body):
    return f"# synthetic\n\n{PIN_HEADING} — synthetic\n\n{body}\n"


def test_the_reader_accepts_a_citation_that_does_resolve():
    section = pin_section(a_ledger(
        f"| 1 | holds | `{REAL_MODULE}{JOINER}{REAL_CLASS}"
        f"{JOINER}{REAL_METHOD}` |"))

    assert findings(section) == []


def test_a_path_that_does_not_resolve_is_flagged():
    section = pin_section(a_ledger(
        f"| 1 | holds | `ubb-platform/api/v1/tests/test_gone.py"
        f"{JOINER}{REAL_CLASS}` |"))

    problems = findings(section)

    assert len(problems) == 2, problems
    assert "is not a file" in problems[0]
    assert REAL_CLASS in problems[1]


def test_a_case_no_cited_module_defines_is_flagged():
    section = pin_section(a_ledger(
        f"| 1 | holds | `{REAL_MODULE}{JOINER}RenamedAwayTest` |"))

    problems = findings(section)

    assert len(problems) == 1, problems
    assert "RenamedAwayTest" in problems[0]


def test_a_pytest_style_class_is_checked_and_not_skipped():
    """The go-narrow shape, refused at its own address.

    Under the ADR walker's narrower pattern `TestRenamedAway` matches nothing
    and this section passes while citing a class no module defines.
    """
    section = pin_section(a_ledger(
        f"| 1 | holds | `{REAL_MODULE}{JOINER}TestRenamedAway` |"))

    problems = findings(section)

    assert len(problems) == 1, problems
    assert "TestRenamedAway" in problems[0]


def test_a_continuation_span_is_bound_to_the_row_above_it():
    """`::method` on its own resolves against the section's modules."""
    section = pin_section(a_ledger(
        f"| 1 | holds | `{REAL_MODULE}{JOINER}{REAL_CLASS}`, "
        f"`{JOINER}{REAL_METHOD}` |"))

    assert findings(section) == []


def test_a_missing_heading_reads_as_absent_rather_than_empty():
    assert pin_section("# synthetic\n\nno section here\n") is None


def test_an_abbreviated_path_is_flagged():
    section = pin_section(a_ledger(
        f"| 1 | holds | `api/v1/tests/test_one_rule_pins.py"
        f"{JOINER}{REAL_CLASS}` |"))

    assert abbreviated(section) == ["api/v1/tests/test_one_rule_pins.py"]


def test_a_bare_module_name_in_prose_is_left_alone():
    """`flags.py` is a sentence naming a module, not a citation."""
    section = pin_section(a_ledger("| 1 | read only through `flags.py` |"))

    assert abbreviated(section) == []
