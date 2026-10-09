"""Every scenario Seam C runs, declared (#582).

**This table is the extension point.** A capability ticket adds the scenario
its runtime path needs by adding a `Scenario` to `SCENARIOS`, and changes
nothing in the harness:

* `configure` declares the tenant's configuration through its routes —
  registries, books, customers, pools — and returns the selection the
  Blueprint is resolved for;
* `works` is what the customer's code does, per target: each unit of work it
  runs, in order, as data (`_customer.Work`), with only runtime values in it;
* `expect` asserts what the runs did and what the application recorded;
* `readiness` is what the resolved Blueprint must be before anything runs:
  `complete` runs as a lifecycle, anything else only to prove it fails fast;
* `shells` is where a shell artifact runs: dash and bash unless the scenario
  names the whole standing matrix (`MATRIX`).

#583 added a supplier cost read off the response (`provider_response`)
against fixtures in `provider_responses/`, a currency read beside it that the
server refuses, and a cost written as a float that neither target sends
(scenarios 6 to 8); #584 adds a constant Measurement;
#585 extended two declarations rather than adding a scenario: #569's names in
`_customer.STOP_METADATA` (what a Python process reports of a stop) and
their values in `_the_stop`, which both stop scenarios assert through, each
worked out from the scenario's own configuration; #586 a fixed-price kind
against a price declared through #553's publish act.

**Costs are known on purpose.** An unresolved cost adds nothing to a unit of
work's total (`work/services.py`), so a configuration without Cost Rates can
neither cross a ceiling nor produce a posting with a figure to check: every
calculated Event Type here has a rate for every quantity it requires.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Callable, Mapping

from apps.metering.pricing.receipts import REPORTED_COST_SOURCE_KIND_KEY
from apps.metering.usage.models import Posting, PostingMeasurement
from apps.platform.event_types.reported_cost import to_micros
from apps.platform.work import reasons
from core.vocabulary import (
    AFFORDABILITY_REASON_CUSTOMER_SPEND_POOL_EXCEEDED,
    AMOUNT_REPRESENTATION_MAJOR_UNITS_DECIMAL,
    AMOUNT_REPRESENTATION_MINOR_UNITS, CODE_TARGET_PYTHON_SDK,
    CODE_TARGET_SHELL_HTTP, COSTING_STATUS_KNOWN,
    OUTCOME_REASON_EXECUTION_FAILED, PRICING_STATUS_KNOWN,
    SOURCE_KIND_CALLER_SUPPLIED, SOURCE_KIND_PROVIDER_RESPONSE,
    TASK_STATUS_ACTIVE, TASK_STATUS_COMPLETED,
    TASK_STATUS_FAILED, TASK_STATUS_KILLED, TRIGGER_SOURCE_USAGE_INGEST)

from _customer import CustomerId, Record, Response, Subtask, Work
from _harness import COMPLETE, PROVIDER_RESPONSES, Artifact, Ran, catalogue
from _tenant import ScenarioTenant

PYTHON = CODE_TARGET_PYTHON_SDK
SHELL = CODE_TARGET_SHELL_HTTP
BOTH = (PYTHON, SHELL)


# ---------------------------------------------------------------------------
# Where a shell artifact runs
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Shell:
    """A shell command in one of the pinned images under `images/`."""

    image: str
    command: str

    @property
    def name(self) -> str:
        return f"{self.command}@{self.image}"


#: Debian's `sh`, which is dash: the POSIX shell the file is written for.
DASH = Shell("shell", "sh")
#: The shell most people type into.
BASH = Shell("shell", "bash")
#: Where every shell scenario runs.
EVERY_SHELL_SCENARIO = (DASH, BASH)
#: The standing matrix (ADR-0017): dash, bash 5.2, bash 3.2 — what macOS
#: ships — and the oldest jq the file says it runs with. The lifecycle and
#: both stops run in all of it.
MATRIX = (DASH, BASH, Shell("bash-3.2", "bash"), Shell("oldest-jq", "sh"))


# ---------------------------------------------------------------------------
# The suppliers, and their responses
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Supplier:
    """A supplier, the shape of its response, and where its two token counts
    sit in it. The response is `provider_responses/<shape>.json`."""

    shape: str
    provider: str
    input: tuple[str, ...]
    output: tuple[str, ...]

    @property
    def response(self) -> Response:
        return Response(self.shape)


#: A Python library's object, read attribute by attribute.
OPENAI = Supplier("openai.responses.python.v1", "openai",
                  ("usage", "input_tokens"), ("usage", "output_tokens"))
#: A web API's JSON, read key by key — the one shape a shell file reads.
GEMINI = Supplier("google.gemini.rest.v1", "google",
                  ("usageMetadata", "promptTokenCount"),
                  ("usageMetadata", "candidatesTokenCount"))

#: The two token counts both responses carry. Read back from the files by
#: `test_the_provider_responses_carry_what_the_scenarios_expect`, so a
#: response edited is a red test there and never a wrong figure here.
INPUT_TOKENS = 1200
OUTPUT_TOKENS = 340


def held_at(response: Response, path: tuple[str, ...]):
    """What `response` holds at `path`, as Python's `json` reads it."""
    value = json.loads((PROVIDER_RESPONSES / f"{response.fixture}.json")
                       .read_text(encoding="utf-8"))
    for segment in path:
        value = value[segment]
    return value


def held_in(supplier: Supplier) -> tuple[int, int]:
    return (held_at(supplier.response, supplier.input),
            held_at(supplier.response, supplier.output))


# ---------------------------------------------------------------------------
# Declarations, through the routes
# ---------------------------------------------------------------------------

def _quantity(source_kind, *, unit="token", path=(), required=True):
    return {"display_name": "", "value_type": "integer", "unit": unit,
            "required_for_costing": required, "source_kind": source_kind,
            "source_path": list(path)}


def _searches():
    return _quantity("caller_supplied", unit="search", required=False)


def _calculated(tenant: ScenarioTenant, supplier: Supplier, *,
                key="chat.completion") -> None:
    """An Event Type costed from two quantities read off the supplier's
    response and one the caller supplies."""
    tenant._event_type(
        key, provider=supplier.provider, shape=supplier.shape,
        measurements={
            "input_tokens": _quantity("provider_response",
                                      path=supplier.input),
            "output_tokens": _quantity("provider_response",
                                       path=supplier.output),
            "searches": _searches()})


def _reported(tenant: ScenarioTenant, *, key="web.search") -> None:
    """An Event Type costed from the supplier's own figure, which the
    caller supplies as a decimal of the major unit."""
    tenant._event_type(
        key, costing_method="reported", provider="serpapi",
        measurements={"searches": _searches()},
        mapping={"source_kind": "caller_supplied",
                 "amount_representation":
                     AMOUNT_REPRESENTATION_MAJOR_UNITS_DECIMAL,
                 "currency": "usd"})


@dataclass(frozen=True)
class Rates:
    """Micros per unit of each quantity, and what one recorded response
    costs at those rates with `searches` searches."""

    input: int
    output: int
    searches: int

    def rules(self):
        return (("add", "input_tokens", self.input),
                ("add", "output_tokens", self.output),
                ("add", "searches", self.searches))

    def cost(self, searches: int) -> int:
        return (INPUT_TOKENS * self.input + OUTPUT_TOKENS * self.output
                + searches * self.searches)


#: A markup of 50% over cost, in micro-percent.
HALF_AGAIN = 50_000_000


def _marked_up(cost: int) -> int:
    return cost + cost // 2


# ---------------------------------------------------------------------------
# What a run left behind
# ---------------------------------------------------------------------------

@dataclass
class Outcome:
    """What one scenario did on one target: the tenant it ran for, the
    artifact it ran, and each run's result, in order."""

    target: str
    tenant: ScenarioTenant
    artifact: Artifact
    runs: list[Ran]

    def postings(self) -> dict[str, Posting]:
        """Every posting the tenant holds, by the key it was sent under."""
        held = Posting.objects.filter(tenant=self.tenant.tenant)
        return {posting.idempotency_key: posting for posting in held}

    def measured(self, posting: Posting) -> dict:
        return PostingMeasurement.objects.get(posting=posting).measurements


@dataclass(frozen=True)
class Scenario:
    name: str
    configure: Callable[[ScenarioTenant, str], dict]
    works: Callable[[str], tuple[Work, ...]]
    expect: Callable[[Outcome], None]
    targets: tuple[str, ...] = BOTH
    posture: Mapping[str, object] = field(default_factory=dict)
    readiness: str = COMPLETE
    shells: tuple[Shell, ...] = EVERY_SHELL_SCENARIO


# ---------------------------------------------------------------------------
# 1. A representative lifecycle
# ---------------------------------------------------------------------------
#
# Start, a Subtask, usage on the work and in the Subtask, both acknowledged,
# both closed delivered. One Event Type is costed from the supplier's
# response at known rates, the other from the figure the caller supplies.
# Python hands over a Python library's object; shell, a web API's JSON.

LIFECYCLE_SUPPLIER = {PYTHON: OPENAI, SHELL: GEMINI}
LIFECYCLE_RATES = Rates(input=3, output=5, searches=7)
#: What the caller reports the search cost, as text in the major unit.
REPORTED = "0.5"
REPORTED_MICROS = 500_000


def _lifecycle_configuration(tenant: ScenarioTenant, target: str) -> dict:
    supplier = LIFECYCLE_SUPPLIER[target]
    tenant._grouping_fields(("environment", "task"), ("phase", "subtask"))
    tenant._kinds(
        {"key": "report_generation", "uncapped": True,
         "required_grouping_fields": ["environment"]},
        {"key": "summarise", "kind": "subtask", "uncapped": True,
         "required_grouping_fields": ["phase"]})
    _calculated(tenant, supplier)
    _reported(tenant)
    tenant._cost_rules(*LIFECYCLE_RATES.rules(), provider=supplier.provider)
    tenant._markup(HALF_AGAIN)
    tenant.customer("acme")
    return {"task_type": "report_generation",
            "event_types": ["chat.completion", "web.search"],
            "subtask_types": ["summarise"]}


def _lifecycle_work(target: str) -> tuple[Work, ...]:
    return (Work(
        customer="acme",
        values={"idempotency_key": "nightly-report-1",
                "environment": "production"},
        does=(
            Record("chat.completion", {
                "idempotency_key": "chat-1",
                "response": LIFECYCLE_SUPPLIER[target].response,
                "searches": 2}),
            Subtask("summarise",
                    {"idempotency_key": "summarise-1", "phase": "draft"},
                    records=(Record("web.search", {
                        "idempotency_key": "search-1",
                        "reported_cost": REPORTED,
                        "searches": 1}),)),
        )),)


def _a_delivered_lifecycle(outcome: Outcome) -> None:
    (ran,) = outcome.runs
    assert ran.status == 0, ran
    said = ran.said
    chat_cost = LIFECYCLE_RATES.cost(searches=2)

    # The records, by the keys the customer's code sent.
    postings = outcome.postings()
    assert sorted(postings) == ["chat-1", "search-1"], ran
    chat, search = postings["chat-1"], postings["search-1"]
    assert str(chat.task_id) == said["task_id"]
    assert str(search.task_id) == said["subtask_id"]
    assert (chat.event_type, chat.provider) == (
        "chat.completion", LIFECYCLE_SUPPLIER[outcome.target].provider)
    assert outcome.measured(chat) == {"input_tokens": INPUT_TOKENS,
                                      "output_tokens": OUTPUT_TOKENS,
                                      "searches": 2}
    assert (chat.costing_status, chat.provider_cost_micros) == (
        COSTING_STATUS_KNOWN, chat_cost)
    assert (chat.pricing_status, chat.billed_cost_micros) == (
        PRICING_STATUS_KNOWN, _marked_up(chat_cost))
    assert (search.event_type, search.provider) == ("web.search", "serpapi")
    assert (search.costing_status, search.provider_cost_micros) == (
        COSTING_STATUS_KNOWN, REPORTED_MICROS)
    assert (search.pricing_status, search.billed_cost_micros) == (
        PRICING_STATUS_KNOWN, _marked_up(REPORTED_MICROS))
    # The caller's figure arrived on the caller's field, and the record says
    # so — scenario 6 is the same assertion for a figure read off a response.
    assert getattr(search, Posting.RECEIPT_COLUMN)["costing"]["detail"][
        REPORTED_COST_SOURCE_KIND_KEY] == SOURCE_KIND_CALLER_SUPPLIED, search

    # The work and its Subtask, as the API answers them: both delivered, and
    # the work's totals carry the Subtask's.
    task = outcome.tenant.task(said["task_id"])
    (subtask,) = task["subtasks"]
    assert subtask["task_id"] == said["subtask_id"]
    for answered in (task, subtask):
        # A delivered close is `completed`, with no reason: one is accepted
        # only where the work did not deliver.
        assert answered["status"] == TASK_STATUS_COMPLETED, answered
        assert answered["outcome_reason"] is None, answered
        assert answered["unresolved_event_count"] == 0, answered
        assert answered["unpriced_event_count"] == 0, answered
    assert (subtask["event_count"], subtask["total_provider_cost_micros"],
            subtask["total_billed_cost_micros"]) == (
        1, REPORTED_MICROS, _marked_up(REPORTED_MICROS))
    assert (task["event_count"], task["total_provider_cost_micros"],
            task["total_billed_cost_micros"]) == (
        2, chat_cost + REPORTED_MICROS,
        _marked_up(chat_cost) + _marked_up(REPORTED_MICROS))


REPRESENTATIVE_LIFECYCLE = Scenario(
    name="lifecycle",
    posture={"products": ["metering", "billing"],
             "billing_mode": "postpaid"},
    configure=_lifecycle_configuration,
    works=_lifecycle_work,
    expect=_a_delivered_lifecycle,
    shells=MATRIX,
)


# ---------------------------------------------------------------------------
# What every stop and every refusal is checked against
# ---------------------------------------------------------------------------

TASK_START = ("POST", "/api/v1/tasks")
RECORD_USAGE = ("POST", "/api/v1/metering/usage")

#: The status a shell call returns for a stop, reserved for nothing else
#: (#180 §12; ADR-0017 §4).
STOP_STATUS = 20
#: The status a Python process ends with when an exception reaches its top.
UNCAUGHT = 1
#: What curl returns for an answer of 400 or above (`--fail-with-body`).
CURL_REFUSED = 22


def declared_status(artifact: Artifact, name: str) -> int:
    """A status the rendered shell file declares, read off the file."""
    (status,) = re.findall(rf"^{name}=(\d+)$",
                           artifact.files["ubb_integration.sh"], re.M)
    return int(status)


def _the_stop(outcome: Outcome, ran: Ran, *, key: str, scope: str,
              reason: str, trigger_source: str, bound: int,
              measured: int) -> None:
    """The stop arrived inside a 200 and was acted on: the event that
    carried it is recorded, its metadata names that event, and each target
    hands it over its own way — a status of 20 from shell, logged and passed
    on, never 0; `UBBStopRequested` from Python, logged by the generated
    module and raised to the process's own boundary.

    The metadata is the fields the acknowledgement and the request publish:
    the event, the key, the scope and the reason, and how the stop was
    applied and what it was measured on (#569; #585). The event's id is the
    recorded posting's; every other expected value is the caller's, worked
    out from its scenario's own configuration and never read back from the
    server."""
    tipping = outcome.postings()[key]
    assert "stop_requested" in ran.said, ran
    stop = json.loads(ran.said["stop_requested"])
    assert stop == {"event_id": str(tipping.id), "idempotency_key": key,
                    "stop_scope": scope, "stop_reason": reason,
                    "trigger_source": trigger_source,
                    "stop_bound_micros": bound,
                    "stop_measured_micros": measured}, ran
    if outcome.target == SHELL:
        assert declared_status(outcome.artifact,
                                "UBB_EXIT_STOP_REQUESTED") == STOP_STATUS
        assert ran.status == STOP_STATUS, ran
        assert ran.said["status"] == str(STOP_STATUS), ran
        # The boundary logs it, as JSON, on its own line.
        assert f"stop_requested {ran.said['stop_requested']}" in (
            ran.stderr.splitlines()), ran
        return
    assert ran.status == UNCAUGHT, ran
    assert "UBBStopRequested" in ran.stderr, ran
    # The module's one handler logs the key the event was sent under and
    # each field of the stop by its own name, in the catalogue's words,
    # which the rendered file holds — the whole line, every value in it.
    logged = catalogue()["MESSAGES"]["stop"]
    assert logged in outcome.artifact.files["ubb_integration.py"]
    assert logged % (key, scope, reason, trigger_source, bound,
                     measured) in ran.stderr, ran


def _refused(outcome: Outcome, ran: Ran, *, status: int, code: str,
             **body_extensions) -> None:
    """An answer of `status` was surfaced with its body, and the failure
    kept its own status: curl's from shell, never 20 and never 0, with the
    whole problem body printed — `body_extensions` are checked in it; the
    SDK's error from Python, which carries the status, the code and the
    detail and no extension of the body, so there they are not."""
    if outcome.target == SHELL:
        assert ran.status == CURL_REFUSED, ran
        assert ran.said["status"] == str(CURL_REFUSED), ran
        (body,) = [json.loads(line) for line in ran.stderr.splitlines()
                   if line.startswith("{")]
        assert (body["status"], body["code"]) == (status, code), ran
        assert {name: body.get(name) for name in body_extensions} == (
            body_extensions), ran
        return
    assert ran.status == UNCAUGHT, ran
    assert f"API error {status} [{code}]" in ran.stderr, ran


# ---------------------------------------------------------------------------
# 2. A unit of work crosses its ceiling
# ---------------------------------------------------------------------------
#
# Each response costs 3,000,000 micros at these rates, against a ceiling of
# 5,000,000: the first record is under it, the second crosses it, and the
# third is never sent. A JSON response, so the one configuration runs on both
# targets.

STOP_RATES = Rates(input=2_000, output=1_750, searches=2_500)
CEILING = 5_000_000


def _ceiling_configuration(tenant: ScenarioTenant, target: str) -> dict:
    tenant._kinds({"key": "report_generation",
                   "task_cogs_ceiling_micros": CEILING})
    _calculated(tenant, GEMINI)
    tenant._cost_rules(*STOP_RATES.rules(), provider=GEMINI.provider)
    tenant.customer("acme")
    return {"task_type": "report_generation",
            "event_types": ["chat.completion"]}


def _three_records(customer: str, work_key: str, first: int = 1) -> Work:
    return Work(customer=customer, values={"idempotency_key": work_key},
                does=tuple(Record("chat.completion", {
                    "idempotency_key": f"chat-{number}",
                    "response": GEMINI.response, "searches": 2})
                    for number in range(first, first + 3)))


def _stopped_by_its_ceiling(outcome: Outcome) -> None:
    (ran,) = outcome.runs
    assert STOP_RATES.cost(searches=2) < CEILING <= 2 * STOP_RATES.cost(2)
    assert sorted(outcome.postings()) == ["chat-1", "chat-2"], ran
    # Crossed by this report: the bound is the unit's pinned ceiling, and the
    # amount measured is its supplier total at the crossing — both records.
    _the_stop(outcome, ran, key="chat-2", scope="task",
              reason=reasons.TASK_COGS_CEILING,
              trigger_source=TRIGGER_SOURCE_USAGE_INGEST, bound=CEILING,
              measured=2 * STOP_RATES.cost(searches=2))
    # Nothing was declared after the stop: the platform stopped the work,
    # and neither target turns a stop into an outcome.
    assert ran.requests == [TASK_START, RECORD_USAGE, RECORD_USAGE], ran
    task = outcome.tenant.task(ran.said["task_id"])
    assert task["status"] == TASK_STATUS_KILLED, task
    assert task["outcome_reason"] is None, task
    assert (task["event_count"], task["total_provider_cost_micros"]) == (
        2, 2 * STOP_RATES.cost(searches=2)), task


CEILING_CROSSED = Scenario(
    name="ceiling",
    configure=_ceiling_configuration,
    works=lambda target: (_three_records("acme", "nightly-report-1"),),
    expect=_stopped_by_its_ceiling,
    shells=MATRIX,
)


# ---------------------------------------------------------------------------
# 3. A customer reaches its spend pool
# ---------------------------------------------------------------------------
#
# The other scope a stop has. An enforcing tenant, a markup so each record
# has a price (4,500,000 micros), and a blocking pool of 4,000,000 on the
# customer: the first record crosses it. The stop shares the ceiling's
# status and exception and is told apart by its metadata. The pool then
# holds: the customer's next unit of work is refused at its start.

POOL = 4_000_000
#: Where the pool stops, per cent of its cap: its whole cap.
POOL_HARD_STOP_PCT = 100


def _pool_configuration(tenant: ScenarioTenant, target: str) -> dict:
    tenant._kinds({"key": "support_reply", "uncapped": True})
    _calculated(tenant, GEMINI)
    tenant._cost_rules(*STOP_RATES.rules(), provider=GEMINI.provider)
    tenant._markup(HALF_AGAIN)
    tenant.customer("acme")
    tenant.spend_pool("acme", POOL, hard_stop_pct=POOL_HARD_STOP_PCT)
    return {"task_type": "support_reply", "event_types": ["chat.completion"]}


def _stopped_by_the_customer_pool(outcome: Outcome) -> None:
    stopped, refused = outcome.runs
    assert _marked_up(STOP_RATES.cost(searches=2)) >= POOL
    assert sorted(outcome.postings()) == ["chat-1"], stopped
    # Opened by this report: the bound is the pool's stop line, its cap at
    # the stated share, and the amount measured is the month's billed
    # charges at the crossing — this one record, marked up. The line is
    # worked out here and not by the kernel's own function for it, so the
    # expectation is not the code under test asked again.
    _the_stop(outcome, stopped, key="chat-1", scope="customer",
              reason=reasons.CUSTOMER_SPEND_POOL,
              trigger_source=TRIGGER_SOURCE_USAGE_INGEST,
              bound=POOL * POOL_HARD_STOP_PCT // 100,
              measured=_marked_up(STOP_RATES.cost(searches=2)))
    assert stopped.requests == [TASK_START, RECORD_USAGE], stopped
    task = outcome.tenant.task(stopped.said["task_id"])
    assert task["status"] == TASK_STATUS_KILLED, task
    assert task["outcome_reason"] is None, task
    # The customer is stopped, so the next unit of work is refused at its
    # start (`task_endpoints.start`: 409, the reason named): nothing is
    # recorded and no work exists to close.
    assert refused.requests == [TASK_START], refused
    _refused(outcome, refused, status=409, code="task_start_refused",
             reason=AFFORDABILITY_REASON_CUSTOMER_SPEND_POOL_EXCEEDED)

CUSTOMER_POOL_REACHED = Scenario(
    name="customer-pool",
    posture={"products": ["metering", "billing"],
             "billing_mode": "postpaid", "enforcement_mode": "enforcing"},
    configure=_pool_configuration,
    works=lambda target: (_three_records("acme", "reply-1"),
                          _three_records("acme", "reply-2", first=4)),
    expect=_stopped_by_the_customer_pool,
    shells=MATRIX,
)


# ---------------------------------------------------------------------------
# 4. A call the application refuses
# ---------------------------------------------------------------------------
#
# Inside the work, a record names another customer than the work's — an
# integration mistake made of runtime values alone, which the application
# answers 404. The body is surfaced and the failure keeps its own status.
# What each target does with the work then is its own documented rule: the
# SDK's work block declares an ordinary exception `failed`; the shell
# boundary declares nothing and leaves the work open.

def refusal_configuration(tenant: ScenarioTenant, target: str) -> dict:
    tenant._a_kind("support_reply")
    tenant._event_type("search.run", measurements={"searches": _searches()})
    tenant._cost_rules(("add", "searches", 7), provider="openai")
    tenant.customer("acme")
    tenant.customer("globex")
    return {"task_type": "support_reply", "event_types": ["search.run"]}


def refusal_work(target: str) -> tuple[Work, ...]:
    return (Work(customer="acme", values={"idempotency_key": "reply-1"},
                 does=(
                     Record("search.run", {"idempotency_key": "search-1",
                                           "searches": 1}),
                     Record("search.run", {"idempotency_key": "search-2",
                                           "customer_id": CustomerId("globex"),
                                           "searches": 1}),
                     Record("search.run", {"idempotency_key": "search-3",
                                           "customer_id": CustomerId("acme"),
                                           "searches": 1}),
                 )),)


def _a_refused_record(outcome: Outcome) -> None:
    (ran,) = outcome.runs
    assert sorted(outcome.postings()) == ["search-1"], ran
    _refused(outcome, ran, status=404, code="not_found")
    task = outcome.tenant.task(ran.said["task_id"])
    if outcome.target == SHELL:
        assert ran.requests == [TASK_START, RECORD_USAGE, RECORD_USAGE], ran
        assert task["status"] == TASK_STATUS_ACTIVE, task
        assert any(line.startswith("ubb_run_task: ")
                   for line in ran.stderr.splitlines()), ran
        return
    assert ran.requests[:3] == [TASK_START, RECORD_USAGE, RECORD_USAGE], ran
    assert ran.requests[3][1] == f"/api/v1/tasks/{task['task_id']}/close", ran
    assert (task["status"], task["outcome_reason"]) == (
        TASK_STATUS_FAILED, OUTCOME_REASON_EXECUTION_FAILED), task


REFUSED = Scenario(
    name="refused",
    configure=refusal_configuration,
    works=refusal_work,
    expect=_a_refused_record,
)


# ---------------------------------------------------------------------------
# 5. Artifacts that are not complete fail fast
# ---------------------------------------------------------------------------
#
# Run only to prove it: each fails at its first call that is not ready,
# names what that call is missing, and — the harness checks this for every
# fail-fast run — no call that is not ready reaches the application.

def _says_what_is_missing(outcome: Outcome, ran: Ran,
                          operation: str) -> list[str]:
    """The run named the call that is not ready, in the file's own words,
    and every value that call has none for, and sent the reader to the
    header — which names every blocking diagnostic. Returns the values it
    named, for the scenario to hold to what its configuration lacks."""
    said = catalogue()["MESSAGES"]
    (call,) = [call for call in outcome.artifact.blueprint["calls"]
               if call["operation_id"] == operation
               and call["readiness"] != COMPLETE][:1]
    # "<operation> (<readiness>) is not ready to run. The generated file's
    # header says why." No scenario declares a constant before #584, so every
    # unconfigured value here is one the configuration lacks.
    assert (f"{operation} ({call['readiness']}) {said['notReady']}"
            in ran.stderr), ran
    missing = [argument["name"] for argument in call["arguments"]
               if argument["configured"] is False]
    for name in missing:
        assert f"{name} {said['notConfigured']}." in ran.stderr, ran
    module = next(contents for path, contents
                  in outcome.artifact.files.items()
                  if path.startswith("ubb_integration."))
    blocking = [diagnostic["code"] for diagnostic
                in outcome.artifact.blueprint["diagnostics"]
                if diagnostic["severity"] != "advisory"]
    assert blocking, outcome.artifact.blueprint["diagnostics"]
    for code in blocking:
        assert f'# diagnostic = "{code}"' in module, code
    if outcome.target == SHELL:
        assert ran.status == declared_status(
            outcome.artifact, "UBB_EXIT_NOT_CONFIGURED"), ran
    else:
        assert ran.status == UNCAUGHT, ran
        assert catalogue()["PYTHON"]["notReadyError"] in ran.stderr, ran
    return missing


START_OPERATION = "api_v1_task_endpoints_start_task"
RECORD_OPERATION = "api_v1_metering_endpoints_record_usage"


def _a_lone_record(customer: str, event_type=None, **values) -> Work:
    return Work(customer=customer, values={"idempotency_key": "work-1"},
                does=(Record(event_type, {"idempotency_key": "event-1",
                                           **values}),))


def _nothing_ran(*lacking: str) -> Callable[[Outcome], None]:
    """The start was the call that failed, naming the values in `lacking`:
    nothing at all was sent."""
    def expect(outcome: Outcome) -> None:
        (ran,) = outcome.runs
        assert _says_what_is_missing(
            outcome, ran, START_OPERATION) == list(lacking), ran
        assert ran.requests == [], ran
        assert outcome.postings() == {}, ran
    return expect


def _scaffold_configuration(tenant: ScenarioTenant, target: str) -> dict:
    """A tenant that has selected nothing."""
    tenant.customer("acme")
    return {}


SCAFFOLD = Scenario(
    name="scaffold",
    configure=_scaffold_configuration,
    works=lambda target: (_a_lone_record("acme"),),
    # Nothing selected: the start has no kind of work to name.
    expect=_nothing_ran("task_type"),
    readiness="scaffold",
)


def _blocked_start_configuration(tenant: ScenarioTenant, target: str) -> dict:
    """A kind of work that requires a Grouping Field declared for Subtasks:
    a start of the work can never carry it, so the start is blocked."""
    tenant._grouping_fields(("phase", "subtask"))
    tenant._kinds({"key": "report_generation", "uncapped": True,
                   "required_grouping_fields": ["phase"]})
    tenant._event_type("search.run", measurements={"searches": _searches()})
    tenant.customer("acme")
    return {"task_type": "report_generation", "event_types": ["search.run"]}


BLOCKED = Scenario(
    name="blocked",
    configure=_blocked_start_configuration,
    works=lambda target: (Work(
        customer="acme",
        values={"idempotency_key": "work-1", "phase": "draft"},
        does=(Record("search.run", {"idempotency_key": "event-1",
                                     "searches": 1}),)),),
    # Every value the start sends is configured; what blocks it is the
    # declaration the header names (`required_grouping_field_wrong_scope`).
    expect=_nothing_ran(),
    readiness="blocked",
)


# A shape UBB knows nothing about. `custom` names no representation, so no
# target defines how to read a path off it, and the call that reads one is
# blocked on BOTH targets (#184 §8). The executing half of the acceptance
# criterion — run on a target whose traversal is defined, against a fixture
# of each representation it claims — therefore has nothing to run today.
# THIS IS ITS HOOK: the driver holds the resolved Blueprint to `readiness`
# before anything runs, so the day a renderer defines a traversal for
# `custom` this scenario fails on that target, and that target gets an
# executing scenario with a fixture of the representation it claims.

def _custom_shape_configuration(tenant: ScenarioTenant, target: str) -> dict:
    tenant._a_kind("report_generation")
    tenant._event_type(
        "chat.completion", provider="in-house", shape="custom",
        label="our own model gateway's response",
        measurements={"input_tokens": _quantity(
            "provider_response", path=("usage", "tokens"))})
    tenant.customer("acme")
    return {"task_type": "report_generation",
            "event_types": ["chat.completion"]}


def _the_record_is_blocked(outcome: Outcome) -> None:
    (ran,) = outcome.runs
    blueprint = outcome.artifact.blueprint
    assert [(diagnostic["code"], diagnostic["key"], diagnostic["field"])
            for diagnostic in blueprint["diagnostics"]
            if diagnostic["severity"] == "blocking"] == [
        ("response_shape_not_readable_by_target", "chat.completion",
         "source_shape_id")], blueprint["diagnostics"]
    # Every value the record sends is configured, its path among them: what
    # blocks it is the shape no target can read, which the header names.
    assert _says_what_is_missing(outcome, ran, RECORD_OPERATION) == [], ran
    assert outcome.postings() == {}, ran
    # The start is complete and was sent; the record never was.
    assert ran.requests[0] == TASK_START, ran


CUSTOM_SHAPE = Scenario(
    name="custom-shape",
    configure=_custom_shape_configuration,
    works=lambda target: (_a_lone_record(
        "acme", "chat.completion", response=GEMINI.response),),
    expect=_the_record_is_blocked,
    readiness="blocked",
)


# ---------------------------------------------------------------------------
# 6. A supplier's cost read off the response (#583)
# ---------------------------------------------------------------------------
#
# The supplier's own figure, read by the generated code off the JSON response
# at the declared path, converted once under the declared representation and
# sent on `provider_response_cost_micros`. What is recorded as COGS is the
# fixture's amount, converted by the platform's own definition, and the
# immutable receipt says where the figure came from (#570's provenance). Run in
# the whole standing matrix, jq 1.5 and bash 3.2 included: the file reads the
# amount as the response wrote it, which every jq there can do (#583 B7).

#: A web API's JSON that also says what the call cost: a decimal string of the
#: major unit at `COST_PATH`, in a currency the declaration pins.
BILLED = Response("google.gemini.rest.v1.billed")
COST_PATH = ("billing", "totalCost")

#: The same response billed in euros: an integer of the minor unit, with the
#: currency beside it, which the declaration reads rather than pins.
BILLED_IN_EUROS = Response("google.gemini.rest.v1.billed-in-euros")
EURO_COST_PATH = ("billing", "amountMinor")
EURO_CURRENCY_PATH = ("billing", "currency")


def _response_cost_configuration(tenant: ScenarioTenant, target: str) -> dict:
    tenant._a_kind("grounded_answer")
    tenant._event_type(
        "grounded.search", costing_method="reported",
        provider=GEMINI.provider, shape=GEMINI.shape,
        measurements={"input_tokens": _quantity("provider_response",
                                                path=GEMINI.input)},
        mapping={"source_kind": SOURCE_KIND_PROVIDER_RESPONSE,
                 "amount_representation":
                     AMOUNT_REPRESENTATION_MAJOR_UNITS_DECIMAL,
                 "source_path": list(COST_PATH), "currency": "usd"})
    tenant.customer("acme")
    return {"task_type": "grounded_answer",
            "event_types": ["grounded.search"]}


def _the_cost_read_off_the_response(outcome: Outcome) -> None:
    (ran,) = outcome.runs
    assert ran.status == 0, ran
    # The platform's own conversion of the fixture's own figure: the oracle
    # the generated code is held to, never a number spelled here.
    expected = to_micros(held_at(BILLED, COST_PATH),
                         AMOUNT_REPRESENTATION_MAJOR_UNITS_DECIMAL, "usd")
    assert expected == 4_200
    (search,) = outcome.postings().values()
    assert search.idempotency_key == "event-1"
    assert (search.costing_status, search.provider_cost_micros) == (
        COSTING_STATUS_KNOWN, expected), ran
    assert outcome.measured(search) == {"input_tokens": INPUT_TOKENS}
    # The immutable record says the figure was read off the response, which
    # is the transport it arrived on and no other (#570).
    receipt = getattr(search, Posting.RECEIPT_COLUMN)
    assert receipt["costing"]["detail"][REPORTED_COST_SOURCE_KIND_KEY] == (
        SOURCE_KIND_PROVIDER_RESPONSE), receipt
    task = outcome.tenant.task(ran.said["task_id"])
    assert task["status"] == TASK_STATUS_COMPLETED, task
    assert (task["event_count"], task["total_provider_cost_micros"]) == (
        1, expected), task


RESPONSE_COST = Scenario(
    name="response-cost",
    configure=_response_cost_configuration,
    works=lambda target: (_a_lone_record(
        "acme", "grounded.search", response=BILLED),),
    expect=_the_cost_read_off_the_response,
    shells=MATRIX,
)


# ---------------------------------------------------------------------------
# 7. A currency read off the response that is not the tenant's (#583 D1)
# ---------------------------------------------------------------------------
#
# The response bills in euros, a currency UBB holds, and the tenant's is US
# dollars. The generated code reads the currency, pins it to the code UBB
# holds and sends it as the event's: it carries no copy of the tenant's
# currency, so it refuses nothing here. The one shared rule is the server's,
# which refuses the event (422, no FX), and the artifact surfaces that refusal
# — the SDK's error from Python, curl's status from shell. Nothing is
# recorded. Whether a unit of work was started is each target's own rule for
# an ordinary failure, and is not what this asserts.

def _currency_read_configuration(tenant: ScenarioTenant, target: str) -> dict:
    tenant._a_kind("grounded_answer")
    tenant._event_type(
        "billed.search", costing_method="reported",
        provider=GEMINI.provider, shape=GEMINI.shape, measurements={},
        mapping={"source_kind": SOURCE_KIND_PROVIDER_RESPONSE,
                 "amount_representation": AMOUNT_REPRESENTATION_MINOR_UNITS,
                 "source_path": list(EURO_COST_PATH),
                 "currency_path": list(EURO_CURRENCY_PATH)})
    tenant.customer("acme")
    return {"task_type": "grounded_answer",
            "event_types": ["billed.search"]}


def _a_currency_the_server_refuses(outcome: Outcome) -> None:
    (ran,) = outcome.runs
    assert held_at(BILLED_IN_EUROS, EURO_CURRENCY_PATH) == "EUR"
    assert outcome.tenant.tenant.default_currency.lower() == "usd"
    # Sent — the file refuses no currency UBB holds — and refused there.
    assert RECORD_USAGE in ran.requests, ran
    _refused(outcome, ran, status=422, code="validation_error")
    assert "currency mismatch" in ran.stderr, ran
    # Nothing recorded for it: no Posting at all.
    assert outcome.postings() == {}, ran
    assert not Posting.objects.filter(tenant=outcome.tenant.tenant).exists()


CURRENCY_REFUSED_BY_THE_SERVER = Scenario(
    name="response-currency-refused",
    configure=_currency_read_configuration,
    works=lambda target: (_a_lone_record(
        "acme", "billed.search", response=BILLED_IN_EUROS),),
    expect=_a_currency_the_server_refuses,
    shells=MATRIX,
)


# ---------------------------------------------------------------------------
# 8. A cost the response writes as a float (#583 B6, B7)
# ---------------------------------------------------------------------------
#
# `1e0`: a binary float to Python's `json`, and refused as money, and the
# integer 1 to every jq in the matrix — jq 1.5 and 1.6 make a double of it,
# and 1.7 prints a zero exponent away — so a file that asked jq for the
# number would send a cost. Both targets refuse it before the record is
# sent, in the words that say what to read instead. What becomes of the work
# then is each target's own rule for an ordinary failure, as for scenario 4.

#: The same response, its cost written as a float.
BILLED_AS_A_FLOAT = Response("google.gemini.rest.v1.billed-as-a-float")


def _a_float_refused_before_it_is_sent(outcome: Outcome) -> None:
    (ran,) = outcome.runs
    assert held_at(BILLED_AS_A_FLOAT, COST_PATH) == 1.0
    assert catalogue()["MESSAGES"]["floatRead"] in ran.stderr, ran
    assert RECORD_USAGE not in ran.requests, ran
    assert ran.requests[0] == TASK_START, ran
    assert outcome.postings() == {}, ran
    if outcome.target == SHELL:
        assert ran.status == declared_status(
            outcome.artifact, "UBB_EXIT_VALUE_REFUSED"), ran
    else:
        assert ran.status == UNCAUGHT, ran


COST_WRITTEN_AS_A_FLOAT = Scenario(
    name="response-cost-written-as-a-float",
    configure=_response_cost_configuration,
    works=lambda target: (_a_lone_record(
        "acme", "grounded.search", response=BILLED_AS_A_FLOAT),),
    expect=_a_float_refused_before_it_is_sent,
    shells=MATRIX,
)


SCENARIOS: tuple[Scenario, ...] = (
    REPRESENTATIVE_LIFECYCLE,
    CEILING_CROSSED,
    CUSTOMER_POOL_REACHED,
    REFUSED,
    SCAFFOLD,
    BLOCKED,
    CUSTOM_SHAPE,
    RESPONSE_COST,
    CURRENCY_REFUSED_BY_THE_SERVER,
    COST_WRITTEN_AS_A_FLOAT,
)
