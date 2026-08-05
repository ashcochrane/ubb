"""The cumulative contract-break gate (#195, migration/cutover decision §7.3).

The gate stopped asking "did this pull request break the contract?" and started
asking "has every break since ``api-v1-launch`` been reviewed?". The comparison
itself is oasdiff's job and runs in CI; what is pinned here is the part that has
actually gone wrong twice — deciding **which committed suppression entries are
real**.

``--err-ignore`` suppresses only ERR findings and ``--warn-ignore`` only WARN
ones. A line filed in the wrong file matches nothing and silently suppresses
nothing, which is how seven WARN-level lines once sat in the ERR file doing
nothing while two ERR findings went unrecorded. ``review()`` reports such a line
as **inert**, so the gate turns red instead of the entry lying quietly, and the
same rule mechanically enforces "human metadata is separated from findings":
prose that is not a comment matches no finding either.
"""
import importlib.util
import sys

import pytest

from api.v1.openapi_export import GIT_ROOT

# The gate is a git-root tool, not part of the Django project, so it is loaded
# by path. It must be registered in sys.modules before execution or its
# dataclass cannot resolve its own module.
_SPEC = importlib.util.spec_from_file_location(
    "contract_gate", GIT_ROOT / "openapi" / "contract_gate.py")
contract_gate = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = contract_gate
_SPEC.loader.exec_module(contract_gate)

ERR, WARN = contract_gate.LEVEL_ERR, contract_gate.LEVEL_WARN

HTTP_METHODS = frozenset(
    {"GET", "PUT", "POST", "DELETE", "OPTIONS", "HEAD", "PATCH", "TRACE"})

#: oasdiff's non-operation sections. A finding here carries no operation and no
#: path, so its entry opens with the section instead — see `component_finding`.
SECTIONS = frozenset({"components"})


def finding(operation="GET", path="/api/v1/margin/", text="api path removed "
            "without deprecation", level=ERR):
    """One oasdiff `--format json` finding, trimmed to the fields we read."""
    return {"operation": operation, "path": path, "text": text, "level": level}


def component_finding(text="webhook `billing.balance_low` removed", level=ERR):
    """A COMPONENT-level finding, verbatim in shape from oasdiff 1.23.0.

    Note what is NOT here: `operation` and `path`. That is the whole point —
    the gate read both unconditionally and raised KeyError on the first webhook
    removal since the baseline was tagged, which is to say it could not run at
    all for the change #222 made.
    """
    return {"id": "webhook-removed", "section": "components",
            "text": text, "level": level}


class TestEntryFor:
    """Entries are generated from oasdiff's own output, never hand-typed."""

    def test_entry_is_operation_path_then_verbatim_finding_text(self):
        assert contract_gate.entry_for(finding()) == (
            "GET /api/v1/margin/ api path removed without deprecation")

    def test_generated_entry_suppresses_the_finding_it_came_from(self):
        f = finding(operation="PATCH", path="/api/v1/tenant/config",
                    text="removed the request property `x`", level=WARN)
        assert contract_gate.suppresses(contract_gate.entry_for(f), f)


class TestSuppresses:
    """oasdiff `checker/ignore.go`: the line must contain operation, path and
    text, matched case-insensitively."""

    def test_all_three_parts_present_matches(self):
        assert contract_gate.suppresses(
            "GET /api/v1/margin/ api path removed without deprecation",
            finding())

    def test_matching_is_case_insensitive(self):
        assert contract_gate.suppresses(
            "get /API/V1/margin/ API PATH REMOVED WITHOUT DEPRECATION",
            finding())

    def test_wrong_operation_does_not_match(self):
        assert not contract_gate.suppresses(
            "POST /api/v1/margin/ api path removed without deprecation",
            finding())

    def test_wrong_path_does_not_match(self):
        assert not contract_gate.suppresses(
            "GET /api/v1/other/ api path removed without deprecation",
            finding())

    def test_different_finding_text_does_not_match(self):
        assert not contract_gate.suppresses(
            "GET /api/v1/margin/ removed the required property `x`",
            finding())

    def test_human_metadata_may_ride_on_the_line(self):
        """A reviewed block may carry slice/PR/date context around the finding
        — §7.2 permits the metadata, forbids only a hand-typed finding."""
        assert contract_gate.suppresses(
            "GET /api/v1/margin/ api path removed without deprecation "
            "(#86, pre-live lane)", finding())


class TestParseEntries:
    def test_comments_and_blank_lines_are_not_entries(self):
        text = "# a comment\n\n   \nGET /api/v1/x api path removed\n"
        assert contract_gate.parse_entries(text) == [
            (4, "GET /api/v1/x api path removed")]

    def test_surrounding_whitespace_is_stripped(self):
        assert contract_gate.parse_entries("  GET /api/v1/x removed  \n") == [
            (1, "GET /api/v1/x removed")]

    def test_crlf_checkouts_parse_identically(self):
        """`core.autocrlf` is true on Windows and these files carry no
        `eol=lf` attribute, so a carriage return must not ride into the entry
        and stop it matching."""
        assert contract_gate.parse_entries("# c\r\nGET /api/v1/x removed\r\n") \
            == [(2, "GET /api/v1/x removed")]


class TestReview:
    """The two verdicts: an unreviewed break, and an entry that does nothing."""

    def test_covered_findings_leave_a_clean_report(self):
        report = contract_gate.review(
            [finding()],
            err_entries=[(1, "GET /api/v1/margin/ api path removed without "
                             "deprecation")],
            warn_entries=[])
        assert report.unreviewed == []
        assert report.inert == []
        assert report.ok

    def test_a_finding_no_entry_covers_is_unreviewed(self):
        report = contract_gate.review([finding()], [], [])
        assert report.unreviewed == [finding()]
        assert not report.ok

    def test_warn_level_entry_in_the_err_file_is_inert(self):
        """The historical defect, now a red gate: --err-ignore never sees a
        WARN finding, so the entry suppresses nothing and the break stays
        unreviewed. Both facts are reported."""
        warn_finding = finding(
            operation="POST", path="/api/v1/metering/usage",
            text="removed the request property `product_id`", level=WARN)
        entry = contract_gate.entry_for(warn_finding)

        report = contract_gate.review(
            [warn_finding], err_entries=[(7, entry)], warn_entries=[])

        assert report.inert == [(contract_gate.ERR_IGNORE_NAME, 7, entry)]
        assert report.unreviewed == [warn_finding]
        assert not report.ok

    def test_the_same_entry_in_the_warn_file_is_live(self):
        warn_finding = finding(text="removed the request property `product_id`",
                               level=WARN)
        report = contract_gate.review(
            [warn_finding], err_entries=[],
            warn_entries=[(7, contract_gate.entry_for(warn_finding))])
        assert report.ok

    def test_an_entry_matching_no_finding_at_all_is_inert(self):
        """Covers both a break that no longer exists and hand-typed prose that
        was never a finding — neither may sit in the file unnoticed."""
        report = contract_gate.review(
            [], err_entries=[(3, "GET /api/v1/gone api path removed")],
            warn_entries=[(4, "this line is prose somebody typed")])
        assert report.inert == [
            (contract_gate.ERR_IGNORE_NAME, 3, "GET /api/v1/gone api path "
                                               "removed"),
            (contract_gate.WARN_IGNORE_NAME, 4, "this line is prose somebody "
                                                "typed"),
        ]

    def test_authoring_against_another_baseline_reports_no_inert_entries(self):
        """`--baseline main` compares a slice against the commit before it, so
        entries recorded by *earlier* slices match nothing — correctly, since
        the breaks they cover predate that baseline. Only the gate's own
        baseline can judge an entry dead."""
        report = contract_gate.review(
            [], err_entries=[(1, "GET /api/v1/margin/ api path removed")],
            warn_entries=[], report_inert=False)
        assert report.inert == []
        assert report.ok

    def test_findings_below_warn_are_not_breaking_changes(self):
        """`oasdiff breaking` reports nothing below WARN, and there is no
        ignore file at a lower level — so a finding the severity-levels file
        downgraded to `info` (the ADR-003 open-enum stance: a new response-enum
        value is additive) must be skipped, never treated as an unreviewed
        break the gate can never be made to pass."""
        report = contract_gate.review(
            [finding(text="added the new optional response property `x`",
                     level=1)], err_entries=[], warn_entries=[])
        assert report.unreviewed == []
        assert report.ok

    def test_one_entry_may_cover_several_findings(self):
        removed = "api path removed without deprecation"
        report = contract_gate.review(
            [finding(path="/api/v1/margin/"),
             finding(path="/api/v1/margin/{customer_id}")],
            err_entries=[
                (1, f"GET /api/v1/margin/ {removed}"),
                (2, f"GET /api/v1/margin/{{customer_id}} {removed}")],
            warn_entries=[])
        assert report.ok


class TestComponentLevelFindings:
    """A finding about no operation — the shape a webhook rename produces (#222).

    Every assertion below was settled by running oasdiff 1.23.0 against the real
    baseline, not inferred from its source. The first reading of its matcher was
    that a missing operation and path match anything, on the reasoning that Go's
    `strings.Contains(line, "")` is true of every line; `_cross_check` disproved
    it in one run — a line carrying only the finding text suppresses nothing,
    and one carrying `components` as well suppresses exactly its own finding.
    """

    def test_the_entry_opens_with_the_section_not_with_blanks(self):
        assert contract_gate.entry_for(component_finding()) == (
            "components webhook `billing.balance_low` removed")

    def test_a_generated_entry_suppresses_the_finding_it_came_from(self):
        f = component_finding()
        assert contract_gate.suppresses(contract_gate.entry_for(f), f)

    def test_the_text_alone_suppresses_nothing(self):
        """The reading that shipped would have been green here, and oasdiff
        would have gone on reporting the break as unreviewed."""
        f = component_finding()
        assert not contract_gate.suppresses(f["text"], f)

    def test_an_entry_for_one_webhook_does_not_cover_another(self):
        entry = contract_gate.entry_for(component_finding())
        assert not contract_gate.suppresses(
            entry, component_finding(text="webhook `margin.provider_cost_spike` "
                                          "removed"))

    def test_an_operation_finding_still_ignores_its_section(self):
        """`section` fills the slot only when there is no operation, so an
        operation-level entry does not suddenly have to name `paths` — which
        would make every entry committed before #222 inert at once.
        """
        f = finding() | {"section": "paths"}
        assert contract_gate.entry_for(f) == (
            "GET /api/v1/margin/ api path removed without deprecation")
        assert contract_gate.suppresses(contract_gate.entry_for(f), f)

    def test_a_recorded_component_break_leaves_a_clean_report(self):
        f = component_finding()
        report = contract_gate.review(
            [f], err_entries=[(1, contract_gate.entry_for(f))], warn_entries=[])
        assert report.ok

    def test_an_unrecorded_component_break_is_unreviewed(self):
        f = component_finding()
        report = contract_gate.review([f], err_entries=[], warn_entries=[])
        assert report.unreviewed == [f]


class TestCommittedSuppressionFiles:
    """The committed files, checked without oasdiff — CI runs the real
    comparison, but a hand-typed finding is catchable right here."""

    @pytest.mark.parametrize("name", [contract_gate.ERR_IGNORE_NAME,
                                      contract_gate.WARN_IGNORE_NAME])
    def test_every_entry_is_a_finding_not_prose(self, name):
        """Two legal shapes, and nothing else.

        An OPERATION-level entry opens with an HTTP method and an `/api/v1/`
        path. A COMPONENT-level one opens with its section instead, because the
        finding carries no operation and no path — a webhook is a published
        event, not a route (#222). Widening to admit the second shape is not
        loosening the rule: prose still opens with neither, which is the whole
        thing this test refuses.
        """
        entries = contract_gate.parse_entries(
            (GIT_ROOT / "openapi" / name).read_text(encoding="utf-8"))
        assert entries, f"{name} has no entries — did the baseline move?"
        for lineno, entry in entries:
            head, _, rest = entry.partition(" ")
            assert head in HTTP_METHODS or head in SECTIONS, (
                f"{name}:{lineno} is not a generated finding — human metadata "
                f"belongs on a `#` comment line: {entry!r}")
            if head in HTTP_METHODS:
                assert rest.startswith("/api/v1/"), f"{name}:{lineno}: {entry!r}"
            else:
                assert rest, (
                    f"{name}:{lineno} is a bare section with no finding text — "
                    f"it would suppress every component finding: {entry!r}")

    @pytest.mark.parametrize("name", [contract_gate.ERR_IGNORE_NAME,
                                      contract_gate.WARN_IGNORE_NAME])
    def test_no_duplicate_entries(self, name):
        entries = [e for _, e in contract_gate.parse_entries(
            (GIT_ROOT / "openapi" / name).read_text(encoding="utf-8"))]
        assert len(entries) == len(set(entries))


class TestCiWiring:
    """#195's ruling, pinned: one baseline, one pinned version, one runner.

    The gate compares against the immutable ``api-v1-launch`` tag, not the base
    branch — comparing against the base branch proves only that each step was
    reviewed in isolation, which is how #129's seven path removals reached main
    unreviewed after its `contract` job went red.
    """

    def setup_method(self):
        """The `contract:` job only.

        Scoped by indentation rather than parsed: PyYAML is not in
        requirements.lock.txt, and another job may legitimately mention
        `base_ref` or carry its own tool pin without reddening this gate.
        """
        lines = (GIT_ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8").splitlines()
        start = lines.index("  contract:")
        rest = lines[start + 1:]
        end = next((i for i, line in enumerate(rest)
                    if line.startswith("  ") and not line.startswith("   ")
                    and line.strip()), len(rest))
        self.job = "\n".join(lines[start:start + 1 + end])

    def test_the_breaking_gate_runs_through_the_committed_script(self):
        assert "python openapi/contract_gate.py" in self.job

    def test_the_contract_job_does_not_pin_its_own_oasdiff_version(self):
        """The pin lives in contract_gate.py; CI reads it from there, so the
        version CI installs cannot drift from the version the gate expects."""
        assert "OASDIFF_VERSION:" not in self.job

    def test_the_breaking_gate_does_not_compare_against_the_base_branch(self):
        assert "base_ref" not in self.job

    def test_tags_are_fetched_so_the_baseline_resolves(self):
        assert "fetch-tags: true" in self.job
        assert "fetch-depth: 0" in self.job
