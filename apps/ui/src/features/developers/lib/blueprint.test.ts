import { describe, expect, it } from "vitest";

import {
  INTEGRATION_READINESS_VALUES,
  PRICING_MODE_LABEL_KEYS,
  type ConfigurationObjectKind,
} from "@/lib/vocabulary";

import { loadBlueprintFixture } from "../api/mock-blueprints";
import type { BlueprintArgument, BlueprintCall, BlueprintDiagnostic } from "../api/types";
import {
  announcementsOf,
  apiReferenceUrl,
  copyActionLabel,
  fixFor,
  isNotRenderable,
  placesOf,
  remediationText,
  roleOf,
  screenFor,
  shownValue,
  stalenessOf,
  subjectOf,
  TERMINAL_STOP_EVENTS,
} from "./blueprint";
import { diagnosticCodeLabel } from "./code-builder-words";
import { notRenderableAddresses } from "ubb-codegen";

// ---------------------------------------------------------------------------
// Hand-built tokens, for the cases no platform-written fixture holds. A
// fixture is what the server answered for one configuration; a reader's
// narrowing has to hold for shapes the fixture set never happened to carry.

function known(
  name: string,
  value: unknown,
  objectKind: ConfigurationObjectKind = "event_type",
  key = "e",
): BlueprintArgument {
  return {
    name,
    binding_class: "platform_known",
    value,
    parameter_name: null,
    environment_variable: null,
    configured: true,
    provenance: {
      object_kind: objectKind,
      key,
      published_revision: 2,
      published_at: "2026-09-01T12:00:00+00:00",
    },
  };
}

function runtime(name: string, parameter: string): BlueprintArgument {
  return {
    name,
    binding_class: "runtime_bound",
    value: null,
    parameter_name: parameter,
    environment_variable: null,
    configured: true,
    provenance: null,
  };
}

function aCall(...arguments_: BlueprintArgument[]): BlueprintCall {
  return { operation_id: "api_v1_metering_endpoints_record_usage", readiness: "complete", arguments: arguments_ };
}

function aDiagnostic(overrides: Partial<BlueprintDiagnostic>): BlueprintDiagnostic {
  return {
    severity: "blocking",
    code: "task_type_retired",
    object_kind: "task_type",
    key: "report_generation",
    field: null,
    remediation_request: null,
    ...overrides,
  };
}

describe("what a call does", () => {
  it("names each call of a lifecycle with a Subtask", async () => {
    const blueprint = await loadBlueprintFixture("explicit-subtasks");

    expect(blueprint.calls.map(roleOf)).toEqual([
      "start_task",
      "start_subtask",
      "record_usage",
      "close_task",
    ]);
    expect(blueprint.calls.map(subjectOf)).toEqual([
      "report_generation",
      "summarise",
      "gemini.generate",
      null,
    ]);
  });

  it("names no subject where nothing is selected", async () => {
    const scaffold = await loadBlueprintFixture("scaffold");

    expect(scaffold.calls.map(subjectOf)).toEqual([null, null, null]);
  });
});

describe("where a token sits", () => {
  it("reads a fact on a plain field at the second segment", () => {
    const call = aCall(known("task_type", "k", "task_type", "k"), known("task_type.pricing_mode", "fixed", "task_type", "k"));

    expect(placesOf(call)).toEqual([
      { kind: "field", field: "task_type" },
      { kind: "fact", field: "task_type", element: "pricing_mode", key: null },
    ]);
  });

  // ⚠ A MEASUREMENT MAY BE CODED `unit`. Its value token is `measurements.unit`,
  // two segments — which on a plain field would be the fact `unit`. Read by
  // its last segment alone it would be worded as a unit of measure.
  it("reads a keyed field's second segment as a key, even one named like a fact", () => {
    const call = aCall(
      known("measurements", "unit"),
      runtime("measurements.unit", "unit"),
      known("measurements.unit.unit", "token"),
    );

    expect(placesOf(call)).toEqual([
      { kind: "field", field: "measurements" },
      { kind: "keyed_value", field: "measurements", key: "unit" },
      { kind: "fact", field: "measurements", element: "unit", key: "unit" },
    ]);
  });

  // ⚠ A KEY IS NEVER DECODED OUT OF A NAME. A dot inside a key is encoded in
  // the name; the key itself is the value of the key token before it.
  it("takes a key from its key token, not from the encoded name", () => {
    const call = aCall(
      known("measurements", "x.source_path"),
      runtime("measurements.x%2Esource_path", "x_source_path"),
      known("measurements.x%2Esource_path.value_type", "integer"),
    );

    const places = placesOf(call);

    expect(places[1]).toEqual({ kind: "keyed_value", field: "measurements", key: "x.source_path" });
    expect(places[2]).toEqual({ kind: "fact", field: "measurements", element: "value_type", key: "x.source_path" });
  });
});

describe("how a token's value is shown", () => {
  const show = (argument: BlueprintArgument, call = aCall(argument)) =>
    shownValue(argument, placesOf(call)[call.arguments.indexOf(argument)] ?? { kind: "field", field: argument.name }, false);

  it("shows a credential as the variable that holds it, never a value", async () => {
    const blueprint = await loadBlueprintFixture("calculated-cost");
    const [credential] = blueprint.calls[0]?.arguments ?? [];

    expect(credential && show(credential, blueprint.calls[0])).toEqual({ kind: "secret", variable: "UBB_API_KEY" });
  });

  it("shows a runtime value as the parameter that carries it", () => {
    expect(show(runtime("customer_id", "customer_id"))).toEqual({ kind: "parameter", parameter: "customer_id" });
  });

  it("shows an undeclared literal as not yet declared", async () => {
    const scaffold = await loadBlueprintFixture("scaffold");
    const start = scaffold.calls[0];
    const kind = start?.arguments.find((argument) => argument.name === "task_type");

    expect(kind && start && show(kind, start)).toEqual({ kind: "unconfigured" });
  });

  it("shows a valued constant as declared and not yet generable, never as not declared", async () => {
    // #571: the Blueprint carries the constant unconfigured, and its
    // diagnostic says why. Read alone, the token would say "not declared
    // yet" of a value the tenant declared.
    const constant = await loadBlueprintFixture("constant");
    const addresses = notRenderableAddresses(constant);
    const record = constant.calls.find((call) => call.operation_id === "api_v1_metering_endpoints_record_usage");
    const places = record ? placesOf(record) : [];
    const shownAt = (name: string) => {
      const index = record?.arguments.findIndex((argument) => argument.name === name) ?? -1;
      const argument = record?.arguments[index];
      const place = places[index];
      return argument && place && record
        ? shownValue(argument, place, isNotRenderable(record, place, addresses))
        : undefined;
    };

    expect([...addresses]).toEqual(["flat.call:flat_fee"]);
    expect(shownAt("measurements.flat_fee")).toEqual({ kind: "not_renderable" });
    // The quantity beside it is the caller's, and is shown as that.
    expect(shownAt("measurements.searches")).toEqual({ kind: "parameter", parameter: "searches" });
    // Addressed to another Event Type's quantity of the same code, the token
    // reads as it did before #571: the match needs the Event Type too.
    const at = record?.arguments.findIndex((argument) => argument.name === "measurements.flat_fee") ?? -1;
    const token = record?.arguments[at];
    const place = places[at];
    const elsewhere = new Set(["another.call:flat_fee"]);
    const marked = record && place ? isNotRenderable(record, place, elsewhere) : undefined;
    expect(marked).toBe(false);
    expect(token && place ? shownValue(token, place, marked === true) : undefined).toEqual({ kind: "unconfigured" });
  });

  it("words a fact through its registry concept", () => {
    const call = aCall(known("task_type", "k", "task_type", "k"), known("task_type.pricing_mode", "fixed", "task_type", "k"));
    const fact = call.arguments[1];

    expect(fact && show(fact, call)).toEqual({ kind: "concept", labelKeys: PRICING_MODE_LABEL_KEYS, value: "fixed" });
  });

  it("states a capped kind's figure, and a capped kind declaring none", () => {
    const figure = aCall(known("task_type", "k", "task_type", "k"), known("task_type.task_cogs_ceiling_micros", 5_000_000, "task_type", "k"));
    const none = aCall(known("task_type", "k", "task_type", "k"), known("task_type.task_cogs_ceiling_micros", null, "task_type", "k"));

    expect(figure.arguments[1] && show(figure.arguments[1], figure)).toEqual({ kind: "money", micros: 5_000_000 });
    expect(none.arguments[1] && show(none.arguments[1], none)).toEqual({ kind: "no_ceiling_declared" });
  });

  it("states a flag in words", () => {
    const call = aCall(known("task_type", "k", "task_type", "k"), known("task_type.uncapped", true, "task_type", "k"));

    expect(call.arguments[1] && show(call.arguments[1], call)).toEqual({ kind: "words", text: "Uncapped" });
  });

  it("shows a path into a response a segment at a time", () => {
    const call = aCall(known("measurements", "tokens"), runtime("measurements.tokens", "response"), known("measurements.tokens.source_path", ["usage", "total"]));

    expect(call.arguments[2] && show(call.arguments[2], call)).toEqual({ kind: "path", segments: ["usage", "total"] });
  });

  // ⚠ A VALUE NOT OF ITS FACT'S SHAPE IS SHOWN AS THE DOCUMENT HOLDS IT. A
  // number where a concept's word belongs is not worded, and a string where a
  // figure belongs is not formatted as money.
  it("shows a value of the wrong shape as it is, never coerced", () => {
    const call = aCall(
      known("task_type", "k", "task_type", "k"),
      known("task_type.pricing_mode", 7, "task_type", "k"),
      known("task_type.task_cogs_ceiling_micros", "5000000", "task_type", "k"),
    );

    expect(call.arguments[1] && show(call.arguments[1], call)).toEqual({ kind: "text", text: "7" });
    expect(call.arguments[2] && show(call.arguments[2], call)).toEqual({ kind: "text", text: "5000000" });
  });

  it("shows a tenant's own key exactly as they declared it", async () => {
    const odd = await loadBlueprintFixture("odd-names");
    const record = odd.calls[1];
    const eventType = record?.arguments.find((argument) => argument.name === "event_type");

    expect(eventType && record && show(eventType, record)).toEqual({ kind: "text", text: "it's a $5 chat-completion" });
  });
});

describe("where a fact can be changed", () => {
  it("points a kind of work at its own page", async () => {
    const blueprint = await loadBlueprintFixture("explicit-subtasks");
    const kinds = blueprint.calls.slice(0, 2).map((call) => {
      const places = placesOf(call);
      const index = call.arguments.findIndex((argument) => argument.name === "task_type");
      const argument = call.arguments[index];
      const place = places[index];
      return argument && place ? screenFor(argument, place) : null;
    });

    expect(kinds).toEqual([
      { to: "/tasks/kinds/$key", params: { key: "report_generation" } },
      { to: "/tasks/kinds/$key", params: { key: "summarise" } },
    ]);
  });

  it("points a capped kind with no figure of its own at the workspace default", () => {
    const call = aCall(known("task_type", "k", "task_type", "k"), known("task_type.task_cogs_ceiling_micros", null, "task_type", "k"));
    const [first, second] = placesOf(call);

    expect(call.arguments[1] && second && screenFor(call.arguments[1], second)).toEqual({ to: "/tasks" });
    expect(call.arguments[0] && first && screenFor(call.arguments[0], first)).toEqual({
      to: "/tasks/kinds/$key",
      params: { key: "k" },
    });
  });

  it("points a calculated cost at its Cost Rates, and a reported one nowhere", () => {
    const calculated = aCall(known("event_type", "e"), known("event_type.costing_method", "calculated"));
    const reported = aCall(known("event_type", "e"), known("event_type.costing_method", "reported"));

    expect(calculated.arguments[1] && screenFor(calculated.arguments[1], placesOf(calculated)[1] ?? { kind: "field", field: "" })).toEqual({ to: "/pricing" });
    expect(reported.arguments[1] && screenFor(reported.arguments[1], placesOf(reported)[1] ?? { kind: "field", field: "" })).toBeNull();
  });

  it("points no API-only declaration at a screen", async () => {
    const blueprint = await loadBlueprintFixture("explicit-subtasks");
    const record = blueprint.calls[2];
    if (!record) throw new Error("the fixture has a record");
    const places = placesOf(record);
    const screens = record.arguments.flatMap((argument, index) => {
      const place = places[index];
      return place ? [screenFor(argument, place)] : [];
    });

    expect(screens.filter((screen) => screen !== null)).toEqual([{ to: "/pricing" }]);
  });
});

describe("what answers a diagnostic", () => {
  it("asks for a choice where nothing is selected", async () => {
    const scaffold = await loadBlueprintFixture("scaffold");

    expect(scaffold.diagnostics.map(fixFor)).toEqual([{ kind: "select" }, { kind: "select" }]);
  });

  it("offers the server's request for an object with no console screen", async () => {
    const blocked = await loadBlueprintFixture("blocked");
    // The one code reported over a complete declaration, where nothing is the
    // thing to change: the server sends no request for it (#571).
    const withAFix = blocked.diagnostics.filter((d) => d.code !== "constant_measurement_not_renderable");

    expect(withAFix.length).toBeGreaterThan(0);
    expect(withAFix.length).toBe(blocked.diagnostics.length - 1);
    for (const diagnostic of withAFix) {
      expect(fixFor(diagnostic)).toEqual({ kind: "request", request: diagnostic.remediation_request });
    }
  });

  it("offers nothing to change for a valid constant, and says only this version cannot use it", async () => {
    const constant = await loadBlueprintFixture("constant");

    expect(constant.diagnostics.map((d) => d.code)).toEqual(["constant_measurement_not_renderable"]);
    expect(constant.diagnostics.map(fixFor)).toEqual([{ kind: "none" }]);
    const label = diagnosticCodeLabel("constant_measurement_not_renderable");
    expect(label).toContain("valid platform configuration");
    expect(label).toContain("this Code Builder version cannot yet generate");
    expect(label).not.toMatch(/missing|not declared|no declared value|unsupported/i);
  });

  it("points a kind of work at its page, or at Tasks where it is not declared", () => {
    expect(fixFor(aDiagnostic({ code: "task_type_retired", key: "report_generation" }))).toEqual({
      kind: "screen",
      screen: { to: "/tasks/kinds/$key", params: { key: "report_generation" } },
    });
    expect(fixFor(aDiagnostic({ code: "task_type_retired", object_kind: "subtask_type", key: "summarise" }))).toEqual({
      kind: "screen",
      screen: { to: "/tasks/kinds/$key", params: { key: "summarise" } },
    });
    expect(fixFor(aDiagnostic({ code: "task_type_not_declared", key: "nope" }))).toEqual({
      kind: "screen",
      screen: { to: "/tasks" },
    });
  });

  it("offers nothing where the diagnostic carries nothing", () => {
    expect(
      fixFor(aDiagnostic({ code: "required_grouping_field_retired", object_kind: "grouping_field", key: "env" })),
    ).toEqual({ kind: "none" });
  });

  it("writes a request as its operation, method, route and body, with no host", () => {
    expect(
      remediationText({
        method: "PATCH",
        route: "/api/v1/event-types/chat.completion",
        operation_id: "api_v1_event_type_endpoints_revise_event_type",
        body: { source_shape_id: "" },
      }),
    ).toBe(
      '# operation_id = "api_v1_event_type_endpoints_revise_event_type"\n' +
        'PATCH /api/v1/event-types/chat.completion\n\n{\n  "source_shape_id": ""\n}\n',
    );
    expect(
      remediationText({
        method: "POST",
        route: "/api/v1/event-types/draft.only/publish",
        operation_id: "api_v1_event_type_endpoints_publish_event_type",
        body: null,
      }),
    ).toBe(
      '# operation_id = "api_v1_event_type_endpoints_publish_event_type"\n' +
        "POST /api/v1/event-types/draft.only/publish\n",
    );
  });

  it("links an operation to its entry in the API reference", () => {
    expect(apiReferenceUrl("https://ubb.example", "api_v1_event_type_endpoints_publish_event_type")).toBe(
      "https://ubb.example/api/v1/docs#/default/api_v1_event_type_endpoints_publish_event_type",
    );
  });
});

describe("what a kind's limits can announce", () => {
  it("names the terminal events of each kind the Blueprint starts, with why each ends the work", async () => {
    const blueprint = await loadBlueprintFixture("explicit-subtasks");

    expect(announcementsOf(blueprint)).toEqual([
      {
        altitude: "task",
        kind: "report_generation",
        uncapped: false,
        announcements: [
          { event: "task.killed", cause: "spend_stop" },
          { event: "task.expired", cause: "went_quiet" },
        ],
      },
      {
        altitude: "subtask",
        kind: "summarise",
        uncapped: true,
        announcements: [
          { event: "subtask.killed", cause: "spend_stop" },
          { event: "subtask.expired", cause: "went_quiet" },
        ],
      },
    ]);
  });

  it("names none where no kind is selected", async () => {
    expect(announcementsOf(await loadBlueprintFixture("scaffold"))).toEqual([]);
  });

  // The set is typed off the contract (`tsc` refuses one missing or extra);
  // this holds it to the committed document too, both ways, so an event the
  // contract publishes at either altitude is one the page names.
  it("is every event the contract's webhooks section publishes at either altitude", () => {
    const [document] = Object.values(
      import.meta.glob("/src/api/schema.json", { eager: true, import: "default" }),
    );
    const section: unknown =
      typeof document === "object" && document !== null ? Reflect.get(document, "webhooks") : null;
    const published = typeof section === "object" && section !== null ? Object.keys(section) : [];
    const atAnAltitude = published.filter((event) => /^(task|subtask)\./.test(event));

    expect(atAnAltitude.length).toBeGreaterThan(0);
    expect([...TERMINAL_STOP_EVENTS].sort()).toEqual(atAnAltitude.sort());
  });
});

describe("whether held files are stale", () => {
  const FP = (digit: string) => `sha256:${digit.repeat(64)}`;

  it("says nothing until files are taken", async () => {
    expect(stalenessOf(undefined, await loadBlueprintFixture("calculated-cost"))).toEqual({ kind: "nothing_held" });
  });

  it("matches files taken from this very Blueprint", async () => {
    const blueprint = await loadBlueprintFixture("calculated-cost");

    expect(stalenessOf(blueprint.configuration_fingerprint ?? undefined, blueprint)).toEqual({ kind: "current" });
  });

  it("says files taken from another resolution are stale", async () => {
    const blueprint = await loadBlueprintFixture("calculated-cost");

    expect(stalenessOf(FP("0"), blueprint)).toEqual({
      kind: "stale",
      held: FP("0"),
      current: blueprint.configuration_fingerprint,
    });
  });

  it("never matches a draft preview, which has no fingerprint", async () => {
    const draft = await loadBlueprintFixture("draft-preview");

    expect(draft.configuration_fingerprint).toBeNull();
    expect(stalenessOf(FP("0"), draft)).toEqual({ kind: "stale", held: FP("0"), current: null });
  });
});

describe("the copy action's words", () => {
  it("says scaffold until the verdict is complete", () => {
    expect(INTEGRATION_READINESS_VALUES.map((readiness) => [readiness, copyActionLabel(readiness)])).toEqual([
      ["scaffold", "Copy scaffold"],
      ["blocked", "Copy scaffold"],
      ["complete", "Copy integration"],
    ]);
  });
});
