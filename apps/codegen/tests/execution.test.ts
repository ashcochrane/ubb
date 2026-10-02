/**
 * What a rendered module DOES, by running it (#577).
 *
 * The module is written to disk as `render` returned it, imported by a real
 * Python against the SDK in this tree, and pointed at a local server standing
 * where UBB would — through `UBB_BASE_URL`, the one seam the artifact itself
 * documents. Nothing is patched: what reaches the wire is what a tenant's
 * process would send.
 *
 * This is not the execution gate (#582 runs complete artifacts against the
 * real application). It is the renderer's own proof that what it wrote is the
 * SDK's real surface, says what was declared, and stops when told to.
 */
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { render, type RenderedFile } from "../src/index.ts";
import type { ResolvedIntegrationBlueprint } from "../src/blueprint.ts";
import { everyArgument, fixture, FIXTURES, REPO_ROOT } from "./support/fixtures.ts";
import { compiled, reportedCost, run } from "./support/python.ts";
import { factsOf, PYTHON_BRANCH_NAMES, rendered } from "./support/rendered.ts";

interface Sent {
  method: string;
  path: string;
  body: Record<string, unknown>;
  authorization: string;
}

const CONTRACT = JSON.parse(readFileSync(join(REPO_ROOT, "openapi", "v1.json"), "utf-8")) as {
  paths: Record<string, Record<string, { operationId?: string }>>;
  components: { schemas: Record<string, { properties: Record<string, unknown> }> };
};

/** `METHOD /path` for an operationId, read off the committed contract. */
function published(operationId: string): { method: string; path: string } {
  for (const [path, methods] of Object.entries(CONTRACT.paths)) {
    for (const [method, operation] of Object.entries(methods)) {
      if (operation.operationId === operationId) {
        return { method: method.toUpperCase(), path };
      }
    }
  }
  throw new Error(`${operationId} is not an operation of the committed contract`);
}

/** A response object of a Python library: its fields read as attributes. */
const AN_OBJECT = `
class Shaped:
    def __init__(self, **fields):
        self.__dict__.update(fields)
`;

describe("a complete module, run", () => {
  it("starts, records and closes through the operations the Blueprint names", () => {
    const blueprint = fixture("calculated-cost");
    const sent = run<Sent[]>(
      rendered("calculated-cost"),
      `${AN_OBJECT}
integration = load()
response = Shaped(usage=Shaped(input_tokens=1200, output_tokens=340))
with integration.unit_of_work(customer_id="customer-1", idempotency_key="work-1",
                              environment="production") as task:
    integration.record_chat_completion(
        customer_id="customer-1", idempotency_key="call-1",
        task_id=task.task_id, response=response, searches=2)
    task.complete()
result = server.requests
`,
    );

    const [start, record, close] = sent;
    expect(sent).toHaveLength(3);
    expect(start!.body).toEqual({
      customer_id: "customer-1",
      idempotency_key: "work-1",
      task_type: "report_generation",
      grouping_fields: { environment: "production" },
    });
    expect(record!.body).toEqual({
      customer_id: "customer-1",
      idempotency_key: "call-1",
      task_id: "task_1",
      event_type: "chat.completion",
      provider: "openai",
      measurements: { input_tokens: 1200, output_tokens: 340, searches: 2 },
      metadata: {},
    });
    expect(close!.body).toEqual({ outcome: "delivered" });

    // Each request is the operation the Blueprint named for that call.
    const operations = blueprint.calls.map((call) => published(call.operation_id));
    expect(sent.map((request) => request.method)).toEqual(
      operations.map((operation) => operation.method),
    );
    expect(start!.path).toBe(operations[0]!.path);
    expect(record!.path).toBe(operations[1]!.path);
    expect(close!.path).toBe(operations[2]!.path.replace("{task_id}", "task_1"));
  });

  it("sends only keys the operation's request publishes", () => {
    const sent = run<Sent[]>(
      rendered("explicit-subtasks"),
      `
integration = load()
response = {"usageMetadata": {"promptTokenCount": 11},
            "usage_metadata": {"candidates_token_count": 7}}
with integration.unit_of_work(customer_id="c", idempotency_key="w",
                              environment="production") as task:
    with integration.start_subtask_summarise(
            customer_id="c", idempotency_key="w-summary",
            parent_task_id=task.task_id, phase="draft") as subtask:
        integration.record_gemini_generate(
            customer_id="c", idempotency_key="e", task_id=subtask.task_id,
            response=response)
        subtask.complete()
    task.complete()
result = server.requests
`,
    );
    const schemas = CONTRACT.components.schemas;

    const [start, subtask, record] = sent;
    expect(sent).toHaveLength(5);
    expect(subtask!.body).toEqual({
      customer_id: "c",
      idempotency_key: "w-summary",
      parent_task_id: "task_1",
      task_type: "summarise",
      grouping_fields: { phase: "draft" },
    });
    expect(record!.body.task_id).toBe("task_2");
    expect(record!.body.measurements).toEqual({ candidate_tokens: 7, prompt_tokens: 11 });
    for (const [request, schema] of [
      [start!, "StartTaskRequest"],
      [subtask!, "StartTaskRequest"],
      [record!, "RecordUsageRequest"],
    ] as const) {
      const unpublished = Object.keys(request.body).filter(
        (key) => !(key in schemas[schema]!.properties),
      );
      expect(unpublished, schema).toEqual([]);
    }
  });

  it("reads the credential from the environment and nowhere else", () => {
    const answer = run<{ sent: string[]; held: boolean }>(
      rendered("direct-task-events"),
      `
integration = load()
integration.start_task(customer_id="c", idempotency_key="w")
source = (directory / "ubb_integration.py").read_text(encoding="utf-8")
result = {"sent": [request["authorization"] for request in server.requests],
          "held": HARNESS_CREDENTIAL in source}
`,
    );

    expect(answer.sent).toEqual(["Bearer not-a-real-key"]);
    expect(answer.held).toBe(false);
  });

  it("holds no host of its own: with the variable unset or empty it refuses, naming it", () => {
    const answer = run<{ refused: string[]; sent: number; set: string }>(
      rendered("direct-task-events"),
      `
import os
integration = load()
refused = []
for value in (None, ""):
    if value is None:
        del os.environ["UBB_BASE_URL"]
    else:
        os.environ["UBB_BASE_URL"] = value
    try:
        integration.start_task(customer_id="c", idempotency_key="w")
    except integration.UBBEnvironmentNotSet as error:
        refused.append(str(error))
sent = len(server.requests)
os.environ["UBB_BASE_URL"] = "http://127.0.0.1:1/"
result = {"refused": refused, "sent": sent,
          "set": integration._client()._base_url}
`,
    );

    // Not the SDK's own default either, which is a developer's localhost: a
    // file that fell back to it would send production usage to nobody.
    expect(answer.refused).toHaveLength(2);
    for (const message of answer.refused) expect(message).toContain("UBB_BASE_URL");
    expect(answer.sent).toBe(0);
    expect(answer.set).toBe("http://127.0.0.1:1");
  });

  it("raises TypeError, naming it, when a runtime value is left out", () => {
    const answer = run<string[]>(
      rendered("calculated-cost"),
      `
integration = load()
refused = []
for call, arguments in (
        (integration.start_task, {"customer_id": "c", "idempotency_key": "w"}),
        (integration.record_chat_completion,
         {"customer_id": "c", "idempotency_key": "e", "task_id": "t",
          "response": object()})):
    try:
        call(**arguments)
    except TypeError as error:
        refused.append(str(error))
result = refused + [len(server.requests)]
`,
    );

    expect(answer).toHaveLength(3);
    expect(answer[0]).toContain("'environment'");
    expect(answer[1]).toContain("'searches'");
    expect(answer[2]).toBe(0);
  });
});

describe("the stop", () => {
  it("is caught in exactly one place, by name, and raised again", () => {
    expect(PYTHON_BRANCH_NAMES.length).toBeGreaterThanOrEqual(10);
    for (const branch of PYTHON_BRANCH_NAMES) {
      const module = factsOf(branch)["ubb_integration.py"]!;

      expect(module.handlers.filter((handler) => handler.catches === "UBBStopRequested")).toEqual([
        { function: "unit_of_work", catches: "UBBStopRequested", reraises: true },
      ]);
      // Nothing else in the file can catch it: no bare handler, and none
      // wide enough to reach outside Exception.
      const wide = module.handlers.filter(
        (handler) =>
          handler.catches === null ||
          /\b(BaseException|Exception)\b/.test(handler.catches),
      );
      expect(wide, branch).toEqual([]);
    }
  });

  it("is not caught by any function that records", () => {
    // The only other handlers anywhere are the conversion's, which catch a
    // number that will not parse and a currency that is not a string.
    const narrow = ["(InvalidOperation, TypeError, ValueError)", "(AttributeError, KeyError)"];
    for (const branch of PYTHON_BRANCH_NAMES) {
      const module = factsOf(branch)["ubb_integration.py"]!;
      const elsewhere = module.handlers.filter((handler) => handler.function !== "unit_of_work");

      expect(
        elsewhere.filter(
          (handler) =>
            !["_to_micros", "_minor_unit"].includes(handler.function ?? "") ||
            !narrow.includes(handler.catches ?? ""),
        ),
        branch,
      ).toEqual([]);
    }
  });

  it("passes through a tenant's own except Exception and out of the boundary", () => {
    const answer = run<Record<string, unknown>>(
      rendered("calculated-cost"),
      `
import logging
${AN_OBJECT}
from ubb import UBBStopRequested
integration = load()
logged = []
handler = logging.Handler()
handler.emit = lambda record: logged.append(record.getMessage())
logging.getLogger("ubb_integration").addHandler(handler)
server.queue("/api/v1/metering/usage", stop=True, stop_scope="customer",
             stop_reason="customer_spend_pool")
response = Shaped(usage=Shaped(input_tokens=1, output_tokens=1))
swallowed, outcome = False, "nothing was raised"
try:
    with integration.unit_of_work(customer_id="c", idempotency_key="w",
                                  environment="production") as task:
        for attempt in range(3):
            try:
                integration.record_chat_completion(
                    customer_id="c", idempotency_key=f"e{attempt}",
                    task_id=task.task_id, response=response, searches=1)
            except Exception:
                swallowed = True
except UBBStopRequested as stop:
    outcome = [stop.stop_scope, stop.stop_reason, isinstance(stop, Exception)]
result = {"swallowed": swallowed, "outcome": outcome, "logged": logged,
          "paths": [request["path"] for request in server.requests]}
`,
    );

    expect(answer.swallowed).toBe(false);
    expect(answer.outcome).toEqual(["customer", "customer_spend_pool", false]);
    // The event that carried the stop was sent once and never again, and
    // nothing was declared about work the stop interrupted.
    expect(answer.paths).toEqual(["/api/v1/tasks", "/api/v1/metering/usage"]);
    const logged = answer.logged as string[];
    expect(logged).toHaveLength(1);
    // What was logged is the key the stopped event was sent under and what
    // the acknowledgement carried.
    expect(logged[0]).toContain("The event sent as 'e0' was recorded");
    expect(logged[0]).toContain("customer_spend_pool");
    expect(logged[0]).toContain("stop_scope='customer'");
  });

  it("is returned and not raised on the backfill path, which sends when it happened", () => {
    const answer = run<Record<string, unknown>>(
      rendered("direct-task-events"),
      `
from datetime import datetime, timezone
integration = load()
server.queue("/api/v1/metering/usage", stop=True, stop_scope="task",
             stop_reason="task_cogs_ceiling")
acknowledgement = integration.backfill_search_run(
    customer_id="c", idempotency_key="e", task_id="t", searches=3,
    recorded_at=datetime(2026, 8, 1, 9, 30, tzinfo=timezone.utc))
result = {"stop": acknowledgement.stop, "scope": acknowledgement.stop_scope,
          "body": server.requests[0]["body"]}
`,
    );

    expect(answer.stop).toBe(true);
    expect(answer.scope).toBe("task");
    expect((answer.body as Record<string, unknown>).effective_at).toBe(
      "2026-08-01T09:30:00+00:00",
    );
  });

  it('spells the backfill path stop_behavior="return" and the live path "raise"', () => {
    const module = factsOf("direct-task-events")["ubb_integration.py"]!;
    const behaviour = (name: string) =>
      module.functions[name]!.calls.flatMap((call) =>
        "stop_behavior" in call.keywords ? [call.keywords.stop_behavior] : [],
      );

    expect(behaviour("backfill_search_run")).toEqual(["return"]);
    expect(behaviour("backfill_reply_sent")).toEqual(["return"]);
    expect(behaviour("record_search_run")).toEqual(["raise"]);
    expect(rendered("direct-task-events")[0]!.contents).toContain('stop_behavior="return"');
    // The boolean the keyword replaced is spelled nowhere.
    for (const file of rendered("direct-task-events")) {
      expect(file.contents).not.toContain("raise_on_stop");
    }
  });
});

describe("a cost the supplier reports", () => {
  const CASES = join(FIXTURES, "reported-cost-cases.json");

  it("is converted exactly as the platform converts it, case for case", () => {
    const answer = reportedCost(rendered("reported-cost"), CASES);

    expect(answer.amounts).toBeGreaterThan(30);
    expect(answer.currencies).toBeGreaterThan(8);
    expect(answer.disagreements).toEqual([]);
  });

  it("is held to cases that refuse as well as cases that convert", () => {
    const cases = JSON.parse(readFileSync(CASES, "utf-8")) as {
      amounts: { amount: { type: string }; expected: { refused?: string } }[];
      currencies: { expected: { refused?: string } }[];
    };
    const refused = (kind: string) =>
      cases.amounts.filter((entry) => entry.expected.refused === kind).length;

    expect(refused("amount")).toBeGreaterThan(8);
    expect(refused("currency")).toBeGreaterThan(0);
    expect(cases.amounts.filter((entry) => entry.amount.type === "float")).not.toEqual([]);
    expect(cases.currencies.filter((entry) => entry.expected.refused === "currency")).not.toEqual(
      [],
    );
  });

  it("goes on the wire as whole micros, converted once, with the declared currency", () => {
    const answer = run<Record<string, unknown>>(
      rendered("reported-cost"),
      `
integration = load()
integration.record_web_search(customer_id="c", idempotency_key="e",
                              task_id="t", searches=1, reported_cost="0.014")
integration.record_web_search(customer_id="c", idempotency_key="e2",
                              task_id="t", searches=1,
                              reported_cost=Decimal("12.000001"))
result = server.bodies("/api/v1/metering/usage")
`,
    );

    expect(answer).toEqual([
      expect.objectContaining({ provider_cost_micros: 14000, currency: "usd" }),
      expect.objectContaining({ provider_cost_micros: 12000001, currency: "usd" }),
    ]);
  });

  it("refuses a float, an over-precise amount and a missing one before anything is sent", () => {
    const answer = run<{ refused: string[]; sent: number }>(
      rendered("reported-cost"),
      `
integration = load()
refused = []
for amount in (0.014, "0.0000001", None, True):
    try:
        integration.record_web_search(customer_id="c", idempotency_key="e",
                                      task_id="t", searches=1,
                                      reported_cost=amount)
    except integration.ReportedCostNotRepresentable as error:
        refused.append(type(error).__name__)
result = {"refused": refused, "sent": len(server.requests)}
`,
    );

    expect(answer.refused).toHaveLength(4);
    expect(answer.sent).toBe(0);
  });

  it("fails on a currency that disagrees with the declared one", () => {
    const answer = run<string[]>(
      rendered("reported-cost"),
      `
integration = load()
answers = [integration._pin_currency("usd", " USD ")]
try:
    integration._pin_currency("usd", "eur")
except integration.ReportedCostCurrencyRefused as error:
    answers.append(str(error))
result = answers
`,
    );

    expect(answer[0]).toBe("usd");
    expect(answer[1]).toContain("eur");
  });

  it("is absent from a module that reports no cost", () => {
    const module = rendered("calculated-cost")[0]!.contents;

    expect(module).not.toContain("Decimal");
    expect(module).not.toContain("_to_micros");
  });

  it("is never rendered for a cost read off the response, which stays blocked", () => {
    const module = factsOf("blocked")["ubb_integration.py"]!;
    const send = module.functions._send_web_search!;
    const record = send.calls.find((call) => call.callee.endsWith(".record_usage"))!;

    expect(Object.keys(record.keywords)).not.toContain("provider_cost_micros");
    expect(Object.keys(record.keywords)).not.toContain("currency");
  });
});

describe("a module that is not ready", () => {
  it("raises from every call that is not ready, naming what is missing", () => {
    const answer = run<Record<string, string>>(
      rendered("scaffold"),
      `
integration = load()
raised = {}
for name, call in (
        ("start", lambda: integration.start_task(customer_id="c", idempotency_key="w")),
        ("work", lambda: integration.unit_of_work(customer_id="c", idempotency_key="w").__enter__()),
        ("record", lambda: integration.record_usage(customer_id="c", idempotency_key="e", task_id="t"))):
    try:
        call()
    except integration.UBBIntegrationNotReady as error:
        raised[name] = str(error)
raised["sent"] = str(len(server.requests))
result = raised
`,
    );

    expect(answer.start).toContain("api_v1_task_endpoints_start_task (scaffold)");
    expect(answer.start).toContain("task_type has no configured value");
    expect(answer.work).toContain("task_type has no configured value");
    expect(answer.record).toContain("api_v1_metering_endpoints_record_usage (scaffold)");
    expect(answer.record).toContain("event_type has no configured value");
    expect(answer.sent).toBe("0");
  });

  it("still runs the calls that are ready, and refuses the ones that are not", () => {
    const answer = run<Record<string, unknown>>(
      rendered("blocked"),
      `
integration = load()
task = integration.start_task(customer_id="c", idempotency_key="w")
raised = {}
for name in ("record_chat_completion", "record_draft_only", "record_web_search",
             "backfill_chat_completion"):
    call = getattr(integration, name)
    arguments = {"customer_id": "c", "idempotency_key": "e", "task_id": task.task_id}
    if name.endswith("chat_completion"):
        arguments["response"] = object()
    if name == "record_web_search":
        arguments["searches"] = 1
    if name.startswith("backfill"):
        arguments["recorded_at"] = "2026-08-01T09:30:00+00:00"
    try:
        call(**arguments)
    except integration.UBBIntegrationNotReady as error:
        raised[name] = str(error)
result = {"raised": raised,
          "paths": [request["path"] for request in server.requests]}
`,
    );

    const raised = answer.raised as Record<string, string>;
    expect(Object.keys(raised)).toHaveLength(4);
    expect(raised.record_chat_completion).toContain("measurements.flat_fee has no configured value");
    expect(raised.record_draft_only).toContain("(blocked)");
    expect(answer.paths).toEqual(["/api/v1/tasks"]);
  });

  it("sends nothing for a quantity no token gives a value to", () => {
    const module = rendered("blocked")[0]!.contents;

    // The derived quantity's facts are stated; its key is given no value.
    expect(module).toContain('# measurements = "ratio" · event_type "chat.completion"');
    expect(module).not.toMatch(/"ratio":/);
  });
});

describe("declared names", () => {
  const ODD = [
    "it's", "$HOME", "$(whoami)", "back`tick", "back\\slash", 'dou"ble',
    "naïve–日本語", "cache-read", "cache read tokens", "per.cent%", "{braces}",
    "class",
  ];

  /** Each declared quantity the caller supplies, and the parameter for it. */
  function suppliedBy(blueprint: ResolvedIntegrationBlueprint): Map<string, string> {
    const found = new Map<string, string>();
    let key: string | null = null;
    for (const argument of everyArgument(blueprint)) {
      if (argument.name === "measurements") key = argument.value as string;
      else if (
        key !== null &&
        argument.binding_class === "runtime_bound" &&
        argument.name.split(".").length === 2 &&
        argument.parameter_name !== "response"
      ) {
        found.set(key, argument.parameter_name!);
      }
    }
    return found;
  }

  it("reach the wire exactly as they were declared", () => {
    const blueprint = fixture("odd-names");
    const parameters = suppliedBy(blueprint);
    expect([...parameters.keys()].sort()).toEqual([...ODD].sort());
    expect(new Set(parameters.values()).size).toBe(ODD.length);
    // Each quantity is given a number of its own, by its own parameter.
    const given = Object.fromEntries(
      ODD.map((code, index) => [parameters.get(code)!, index + 1]),
    );

    const sent = run<Sent[]>(
      rendered("odd-names"),
      `
import json
integration = load()
given = json.loads(${JSON.stringify(JSON.stringify(given))})
task = integration.start_task(customer_id="c", idempotency_key="w")
record = [name for name in integration.__all__ if name.startswith("record_")]
getattr(integration, record[0])(
    customer_id="c", idempotency_key="e", task_id=task.task_id,
    response={"x-usage": {"total tokens": 99}}, **given)
result = server.requests
`,
    );

    expect(sent[0]!.body.task_type).toBe("report-generation");
    expect(sent[1]!.body.event_type).toBe("it's a $5 chat-completion");
    expect(sent[1]!.body.provider).toBe("o'reilly & co");
    expect(sent[1]!.body.measurements).toEqual({
      ...Object.fromEntries(ODD.map((code, index) => [code, index + 1])),
      "read off a hyphenated key": 99,
    });
  });

  /**
   * NOT a Blueprint the routes answered: the odd-names fixture with one
   * declared name, and every token named under it, replaced by text that
   * would end a line and start a statement if it were ever written
   * unescaped. Whether a registry admits such a name is the registry's
   * business; that the renderer survives one is the renderer's.
   */
  function hostile(): { blueprint: ResolvedIntegrationBlueprint; key: string } {
    const key = `x"\n    raise SystemExit("injected")\n# ${String.fromCharCode(0x2028)} \\`;
    const blueprint = fixture("odd-names");
    for (const argument of everyArgument(blueprint)) {
      if (argument.name === "measurements" && argument.value === "class") argument.value = key;
      if (argument.name.startsWith("measurements.class")) {
        argument.name = argument.name.replace("measurements.class", `measurements.${key}`);
      }
      if (argument.name === "event_type") argument.value = `${argument.value}\r\nimport injected`;
      if (argument.provenance?.object_kind === "event_type") {
        argument.provenance.key = `${argument.provenance.key}\r\nimport injected`;
      }
    }
    return { blueprint, key };
  }

  it("cannot end a line or start a statement, whatever they hold", () => {
    const { blueprint, key } = hostile();
    const files: RenderedFile[] = render(blueprint);

    expect(Object.values(compiled(files)).filter((refusal) => refusal !== null)).toEqual([]);
    const sent = run<Sent[]>(
      files,
      `
integration = load()
name = [name for name in dir(integration) if name.startswith("record_")][0]
import inspect
arguments = {parameter: 1 for parameter in
             inspect.signature(getattr(integration, name)).parameters}
arguments["response"] = {"x-usage": {"total tokens": 99}}
getattr(integration, name)(**arguments)
result = server.requests
`,
    );

    expect(sent).toHaveLength(1);
    expect(Object.keys(sent[0]!.body.measurements as object)).toContain(key);
    expect(sent[0]!.body.event_type).toBe("it's a $5 chat-completion\r\nimport injected");
    const lineEnders = [0x0085, 0x2028, 0x2029, 0x000b, 0x000c].map((unit) =>
      String.fromCharCode(unit),
    );
    for (const file of files) {
      // Nothing that could end a line is written raw, in code or in a comment.
      for (const character of lineEnders) expect(file.contents).not.toContain(character);
      expect(file.contents.split("\r")).toHaveLength(1);
      expect(file.contents).not.toMatch(/^\s*raise SystemExit\("injected"/m);
      expect(file.contents).not.toMatch(/^\s*import injected/m);
    }
  });

  /**
   * NOT a Blueprint the routes answered either: the reported-cost fixture
   * with its caller-supplied quantity's parameter renamed to each name the
   * module uses for something of its own.
   */
  it.each(["_client", "_to_micros", "_pin_currency", "recorded_at", "stop_behavior", "os"])(
    "can never stand in front of one of the module's own names: %s",
    (parameter) => {
      const blueprint = fixture("reported-cost");
      for (const argument of everyArgument(blueprint)) {
        if (argument.parameter_name === "searches") argument.parameter_name = parameter;
      }

      const sent = run<Sent[]>(
        render(blueprint),
        `
integration = load()
integration.record_web_search(customer_id="c", idempotency_key="e", task_id="t",
                              reported_cost="1.5", ${parameter}=7)
import inspect
backfill = inspect.signature(integration.backfill_web_search).parameters
when = [name for name in backfill if name.startswith("recorded_at") and name != ${JSON.stringify(parameter)}][0]
integration.backfill_web_search(customer_id="c", idempotency_key="e2", task_id="t",
                                reported_cost="1.5", ${parameter}=8,
                                **{when: "2026-08-01T09:30:00+00:00"})
result = server.requests
`,
      );

      expect(sent.map((request) => request.body.measurements)).toEqual([
        { searches: 7 },
        { searches: 8 },
      ]);
      expect(sent[0]!.body.provider_cost_micros).toBe(1500000);
      expect(sent[1]!.body.effective_at).toBe("2026-08-01T09:30:00+00:00");
    },
  );

  it("name each function for its declared key, and never share a name", () => {
    const blueprint = fixture("direct-task-events");
    // Two Event Types whose keys differ only where a function name cannot.
    for (const argument of everyArgument(blueprint)) {
      if (argument.name === "event_type" && argument.value === "reply.sent") {
        argument.value = "search-run";
      }
    }
    const names = (files: RenderedFile[]) =>
      [...files[0]!.contents.matchAll(/^def ((?:record|backfill)_\w+)/gm)].map(
        (match) => match[1]!,
      );

    const colliding = names(render(blueprint));
    const alone = names(render(fixture("direct-task-events")));

    expect(alone).toEqual([
      "record_reply_sent", "backfill_reply_sent", "record_search_run", "backfill_search_run",
    ]);
    expect(new Set(colliding).size).toBe(4);
    // Neither keeps the plain name: a function a call site already uses is
    // never silently handed to another Event Type.
    expect(colliding).not.toContain("record_search_run");
    expect(colliding.every((name) => /^(record|backfill)_search_run_[0-9a-f]{8}$/.test(name))).toBe(
      true,
    );
  });
});

describe("the verify script", () => {
  function verify(branch: string, eventType: string, captured: unknown, files = rendered(branch)) {
    return run<{ status: number; output: string }>(
      files,
      `
import json, subprocess, sys
captured = directory / "captured.json"
captured.write_text(json.dumps(json.loads(${JSON.stringify(JSON.stringify(captured))})), encoding="utf-8")
ran = subprocess.run([sys.executable, str(directory / "verify_integration.py"),
                      json.loads(${JSON.stringify(JSON.stringify(eventType))}), str(captured)],
                     capture_output=True, text=True, encoding="utf-8")
result = {"status": ran.returncode, "output": ran.stdout + ran.stderr}
`,
    );
  }

  it("passes a captured response every declared path resolves in", () => {
    const answer = verify("calculated-cost", "chat.completion", {
      usage: { input_tokens: 1200, output_tokens: 340 },
    });

    expect(answer.output).toContain("Every check passed.");
    expect(answer.status).toBe(0);
  });

  it("fails on a path that does not resolve", () => {
    const answer = verify("calculated-cost", "chat.completion", {
      usage: { input_tokens: 1200 },
    });

    expect(answer.status).toBe(1);
    expect(answer.output).toMatch(/FAIL.*"output_tokens".*resolves/);
  });

  it("fails on a quantity that reads a constant zero", () => {
    const answer = verify("calculated-cost", "chat.completion", {
      usage: { input_tokens: 0, output_tokens: 340 },
    });

    expect(answer.status).toBe(1);
    expect(answer.output).toMatch(/FAIL.*"input_tokens".*is not zero/);
  });

  it("fails on a value that is not a number", () => {
    const answer = verify("calculated-cost", "chat.completion", {
      usage: { input_tokens: "1200", output_tokens: true },
    });

    expect(answer.status).toBe(1);
    expect(answer.output).toMatch(/FAIL.*"input_tokens".*is a number/);
    expect(answer.output).toMatch(/FAIL.*"output_tokens".*is a number/);
  });

  it("fails on two quantities read from one field", () => {
    // NOT a Blueprint the routes answered: the second quantity's declared
    // path is pointed at the first one's field.
    const blueprint = fixture("calculated-cost");
    for (const argument of everyArgument(blueprint)) {
      if (argument.name === "measurements.output_tokens.source_path") {
        argument.value = ["usage", "input_tokens"];
      }
    }

    const answer = verify(
      "calculated-cost",
      "chat.completion",
      { usage: { input_tokens: 1200, output_tokens: 340 } },
      render(blueprint),
    );

    expect(answer.status).toBe(1);
    expect(answer.output).toMatch(/FAIL.*"output_tokens".*no other quantity/);
  });

  it("walks a declared name of any spelling, and calls nothing", () => {
    const answer = verify("odd-names", "it's a $5 chat-completion", {
      "x-usage": { "total tokens": 99 },
    });

    expect(answer.output).toContain("Every check passed.");
    expect(answer.status).toBe(0);
    const facts = factsOf("odd-names")["verify_integration.py"]!;
    expect(facts.imports.sort()).toEqual(["json", "sys"]);
  });

  it("says so, and exits clean, where no selected Event Type reads a response", () => {
    const answer = verify("direct-task-events", "reply.sent", {});

    expect(answer.output).toContain("There is nothing to check.");
    expect(answer.status).toBe(0);
  });

  it("names the Event Types it knows when asked for one it does not", () => {
    const answer = verify("calculated-cost", "something.else", {});

    expect(answer.status).toBe(2);
    expect(answer.output).toContain("chat.completion");
  });
});
