"""The cumulative contract-break gate (#195, migration/cutover decision §7.3).

The gate stopped asking "did this pull request break the contract?" and started
asking "has every break since ``api-v1-cutover`` been reviewed?" — the baseline
since the cutover (#190); it was ``api-v1-launch`` before. The comparison
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


def webhook_finding(text="request property `data/costing_status` was restricted "
                         "to a list of enum values", level=ERR):
    """An OPERATION-level finding inside the `webhooks` section, verbatim in
    shape from oasdiff 1.23.0 (#456): it carries an operation and a path, and
    the path is `webhook:<event type>` — a path that never starts with `/`.
    The event here is the usage callback, so this module spells no retired
    event name; the shape is what matters, not which event produced it."""
    return {"id": "request-property-became-enum", "operation": "POST",
            "path": "webhook:usage.recorded", "section": "paths",
            "text": text, "level": level}


class TestWebhookOperationFindings:
    """A finding oasdiff's own ignore pass can never suppress (#456).

    `checker/ignore.go` reads an entry's path as its first field starting with
    `/` and requires it to equal the finding's path; a webhook's is
    `webhook:<event>`, so no entry satisfies it — measured against v1.23.0 with
    six line shapes, none of which suppressed. This gate's matcher has no such
    hole, so the entry is honoured here and the cross-check sets the raw tool's
    report of a COVERED webhook finding aside — and only a covered one.
    """

    def test_a_webhook_operation_finding_is_unsuppressible_by_oasdiff(self):
        assert contract_gate.unsuppressible_by_oasdiff(webhook_finding())

    def test_a_route_finding_and_a_component_finding_are_not(self):
        assert not contract_gate.unsuppressible_by_oasdiff(finding())
        assert not contract_gate.unsuppressible_by_oasdiff(component_finding())

    def test_the_generated_entry_names_the_webhook_path(self):
        assert contract_gate.entry_for(webhook_finding()) == (
            "POST webhook:usage.recorded request property "
            "`data/costing_status` was restricted to a list of enum values")

    def test_this_gate_honours_an_entry_for_it(self):
        f = webhook_finding()
        report = contract_gate.review(
            [f], err_entries=[(1, contract_gate.entry_for(f))], warn_entries=[])
        assert report.ok

    def test_the_cross_check_sets_aside_a_covered_webhook_finding_oasdiff_still_reports(self):
        # Ours: nothing unreviewed. Theirs: the webhook finding, which the raw
        # tool cannot drop. Agreement, because the disagreement is the tool's.
        contract_gate._cross_check(ours=[], theirs=[webhook_finding()])

    def test_an_uncovered_webhook_finding_still_has_to_agree(self):
        # Both report it: agreement. Only ours reports it: a divergence, as for
        # any other finding — the set-aside is for the covered case alone.
        contract_gate._cross_check(ours=[webhook_finding()],
                                   theirs=[webhook_finding()])
        with pytest.raises(SystemExit):
            contract_gate._cross_check(ours=[webhook_finding()], theirs=[])

    def test_a_route_finding_only_oasdiff_reports_is_still_a_divergence(self):
        """The negative control: the set-aside must not widen to routes, where
        the raw tool's ignore pass works and a disagreement is ours to fix."""
        with pytest.raises(SystemExit):
            contract_gate._cross_check(ours=[], theirs=[finding()])


SUPPRESSION_FILES = [contract_gate.ERR_IGNORE_NAME,
                     contract_gate.WARN_IGNORE_NAME]


def committed_entries(name):
    return contract_gate.parse_entries(
        (GIT_ROOT / "openapi" / name).read_text(encoding="utf-8"))


def malformed(entry):
    """Why ``entry`` is not a generated finding, or ``None`` when it is one.

    Three legal shapes, and nothing else. An OPERATION-level entry opens with
    an HTTP method and an `/api/v1/` path — or, since #456, with the method
    and a `webhook:<event>` path, which is how oasdiff locates an
    operation-level finding inside the `webhooks` section (an enum on a payload
    field, say); the event name must be followed by finding text, so a bare
    `POST webhook:x` cannot stand in for one. A COMPONENT-level one opens with
    its section instead, because the finding carries no operation and no path
    — a webhook REMOVAL is about a published event, not a route (#222).
    Widening to admit the second and third shapes is not loosening the rule:
    prose still opens with none of them, which is the whole thing refused.
    """
    head, _, rest = entry.partition(" ")
    if head not in HTTP_METHODS and head not in SECTIONS:
        return ("not a generated finding — human metadata belongs on a `#` "
                "comment line")
    webhook = contract_gate.WEBHOOK_PATH_PREFIX
    if head in HTTP_METHODS and rest.startswith(webhook):
        event, _, text = rest.partition(" ")
        if len(event) <= len(webhook) or not text:
            return ("names a webhook and no finding — it would suppress every "
                    "finding on that event")
    elif head in HTTP_METHODS:
        if not rest.startswith("/api/v1/"):
            return "names an operation on no `/api/v1/` path"
    elif not rest:
        return ("a bare section with no finding text — it would suppress every "
                "component finding")
    return None


class TestCommittedSuppressionFiles:
    """The committed files, checked without oasdiff — CI runs the real
    comparison, but a hand-typed finding is catchable right here.

    ⚠ **THE CUTOVER RESET BOTH FILES TO ZERO ENTRIES (#190), AND ZERO IS
    LEGAL.** This class used to assert that each file HAD entries — "did the
    baseline move?" — because against `api-v1-launch` an empty file could only
    mean a lost one. The baseline did move, to `api-v1-cutover`, and every
    difference those entries covered is inside it now. So what is asserted is
    the reset's truth: the files exist, any entry present is well-formed, and
    the well-formedness rule is shown to refuse each malformed shape on a
    planted line — because with nothing committed to read, the committed-file
    check alone would be a rule with no subject.
    """

    @pytest.mark.parametrize("name", SUPPRESSION_FILES)
    def test_the_file_exists(self, name):
        """The gate reads both files unconditionally; a missing one is a crash
        in CI rather than an empty review."""
        assert (GIT_ROOT / "openapi" / name).is_file(), name

    @pytest.mark.parametrize("name", SUPPRESSION_FILES)
    def test_every_entry_present_is_a_finding_not_prose(self, name):
        faults = [f"{name}:{lineno} {reason}: {entry!r}"
                  for lineno, entry in committed_entries(name)
                  for reason in [malformed(entry)] if reason]
        assert not faults, "\n".join(faults)

    @pytest.mark.parametrize("entry", [
        "this line is prose somebody typed",
        "POST webhook:customer.stop_cleared",
        "components",
        "GET /margin/ api path removed without deprecation",
    ], ids=["prose", "a-bare-webhook", "a-bare-section", "a-path-off-the-api"])
    def test_a_planted_malformed_entry_is_refused(self, entry):
        assert malformed(entry), f"{entry!r} passed as a generated finding"

    @pytest.mark.parametrize("entry", [
        "GET /api/v1/margin/ api path removed without deprecation",
        "POST webhook:billing.balance_low request property `x` was restricted "
        "to a list of enum values",
        "components webhook `billing.balance_low` removed",
    ], ids=["an-operation", "a-webhook-operation", "a-component"])
    def test_each_legal_shape_is_accepted(self, entry):
        """The other half of the planted control: the checker is not refusing
        everything, which would pass the test above for nothing."""
        assert malformed(entry) is None, malformed(entry)

    @pytest.mark.parametrize("name", SUPPRESSION_FILES)
    def test_no_duplicate_entries(self, name):
        entries = [e for _, e in committed_entries(name)]
        assert len(entries) == len(set(entries))


class TestTheCutoverBaseline:
    """The gate measures from `api-v1-cutover`, and a break has nowhere to hide
    (#190, #155 §7.5; G22's third zero).

    The cutover tagged slice 8's merge commit `api-v1-cutover`, pointed the gate
    at it and reset both suppression files. That makes "no unexplained oasdiff
    difference against the new baseline" checkable here in two halves: the
    baseline the gate defaults to is the new tag, and a break the committed
    files do not record is reported, not absorbed. The comparison itself needs
    the pinned oasdiff binary and runs in CI's breaking step, which is G22's
    other site.
    """

    def test_the_gate_compares_against_the_cutover_tag(self):
        assert contract_gate.BASELINE_REF == "api-v1-cutover", (
            "the breaking gate no longer measures from the cutover's baseline; "
            "`api-v1-launch` is never the baseline again, and a new baseline is "
            "a new tag (migration/cutover §7.5)")

    def test_zero_entries_is_a_passing_state_when_nothing_broke(self):
        report = contract_gate.review([], err_entries=[], warn_entries=[],
                                      report_inert=True)
        assert report.ok
        assert report.unreviewed == [] and report.inert == []

    def test_a_planted_break_has_no_suppression_to_hide_behind(self):
        """A break the cutover's baseline does not contain — an ERR and a WARN,
        on a path no reviewed entry could name — is reported against the
        COMMITTED files, so neither file covers more than it records."""
        planted = [finding(path="/api/v1/planted-by-the-cutover-test"),
                   finding(path="/api/v1/planted-by-the-cutover-test",
                           text="request property `x` became required",
                           level=WARN)]
        report = contract_gate.review(
            planted,
            committed_entries(contract_gate.ERR_IGNORE_NAME),
            committed_entries(contract_gate.WARN_IGNORE_NAME))
        assert not report.ok
        assert report.unreviewed == planted


class TestCiWiring:
    """#195's ruling, pinned: one baseline, one pinned version, one runner.

    The gate compares against the immutable ``api-v1-cutover`` tag
    (``api-v1-launch`` until the cutover, #190), not the base branch —
    comparing against the base branch proves only that each step was reviewed
    in isolation, which is how #129's seven path removals reached main
    unreviewed after its `contract` job went red.
    """

    #: The step G15 and G22 name in `gates/manifest.yaml`, which the manifest's
    #: own check resolves against this workflow.
    BREAKING_STEP = "Breaking gate — cumulative vs the api-v1-cutover baseline"

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

    def test_the_breaking_step_compares_against_the_committed_baseline(self):
        """CI names no baseline of its own, so the one it compares against is
        `BASELINE_REF` — which :class:`TestTheCutoverBaseline` pins to the
        cutover's tag. An override here would move the comparison without
        moving either pin."""
        lines = self.job.splitlines()
        named = [i for i, line in enumerate(lines)
                 if line.strip() == f"- name: {self.BREAKING_STEP}"]
        assert len(named) == 1, f"no single step is named {self.BREAKING_STEP!r}"
        assert lines[named[0] + 1].strip() == "run: python openapi/contract_gate.py"
        assert "--baseline" not in self.job

    def test_the_contract_job_does_not_pin_its_own_oasdiff_version(self):
        """The pin lives in contract_gate.py; CI reads it from there, so the
        version CI installs cannot drift from the version the gate expects."""
        assert "OASDIFF_VERSION:" not in self.job

    def test_the_breaking_gate_does_not_compare_against_the_base_branch(self):
        assert "base_ref" not in self.job

    def test_tags_are_fetched_so_the_baseline_resolves(self):
        assert "fetch-tags: true" in self.job
        assert "fetch-depth: 0" in self.job
