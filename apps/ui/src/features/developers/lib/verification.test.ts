// What Verify asks for, what it sends, and how it reads what comes back
// (#581). Every Blueprint and every answer here is one the platform wrote.

import { describe, expect, it } from "vitest";

import { ApiProblem, toApiProblem } from "@/api/problem";
import { MEASUREMENT_VALUE_TYPE_VALUES } from "@/lib/vocabulary";

import { BLUEPRINT_FIXTURE_NAMES, loadBlueprintFixture } from "../api/mock-blueprints";
import {
  loadVerificationFixture,
  VERIFICATION_FIXTURE_NAMES,
  type CommittedVerification,
} from "../api/mock-verifications";
import type { BlueprintVerification, BlueprintVerificationRequest } from "../api/types";
import {
  blankSamples,
  GROUPING_FIELD_REQUIRED,
  groupingFieldsAsked,
  isWholeNumber,
  NOTHING_TO_RUN,
  presentedAsVerified,
  refusalOf,
  sampleProblems,
  standingOf,
  unavailableEventTypesOf,
  verificationKey,
  verificationRequestOf,
  verifyOfferOf,
  WHOLE_NUMBER_REQUIRED,
  type SamplePlan,
  type SampleValues,
} from "./verification";

/** The properties the committed contract publishes on one request schema. */
function publishedProperties(schemaName: string): string[] {
  const [document] = Object.values(
    import.meta.glob("/src/api/schema.json", { eager: true, import: "default" }),
  );
  let node: unknown = document;
  for (const key of ["components", "schemas", schemaName, "properties"]) {
    node = typeof node === "object" && node !== null ? Reflect.get(node, key) : undefined;
  }
  if (typeof node !== "object" || node === null) {
    throw new Error(`the committed contract publishes no ${schemaName}`);
  }
  return Object.keys(node);
}

async function planOf(name: string): Promise<SamplePlan> {
  const offer = verifyOfferOf(await loadBlueprintFixture(name));
  if (offer.kind !== "offered") throw new Error(`${name} is not offered Verify`);
  return offer.plan;
}

/** The samples a developer types to make exactly this request. */
function samplesFor(plan: SamplePlan, request: BlueprintVerificationRequest): SampleValues {
  return {
    groupingFields: plan.groupingFields.map((field) => request.grouping_fields?.[field.key] ?? ""),
    records: plan.records.map((record) => {
      const sent = request.records.find((candidate) => candidate.event_type === record.eventType);
      return {
        included: sent !== undefined,
        subtaskType: sent?.subtask_type ?? "",
        measurements: record.measurements.map((measurement) => {
          const sample = sent?.measurements?.[measurement.code];
          return sample === undefined ? "" : String(sample);
        }),
        providerCost: String(sent?.provider_cost_micros ?? sent?.provider_response_cost_micros ?? ""),
      };
    }),
  };
}

async function committed(): Promise<CommittedVerification[]> {
  return Promise.all(VERIFICATION_FIXTURE_NAMES.map(loadVerificationFixture));
}

async function answered(name: string): Promise<BlueprintVerification> {
  const fixture = await loadVerificationFixture(name);
  if (fixture.kind !== "answered") throw new Error(`${name} is not an answer`);
  return fixture.answer;
}

async function refusedWith(name: string): Promise<ApiProblem> {
  const fixture = await loadVerificationFixture(name);
  if (fixture.kind !== "refused") throw new Error(`${name} is not a refusal`);
  return toApiProblem(fixture.problem);
}

describe("whether Verify is offered", () => {
  it("is offered for a stored, complete Blueprint", async () => {
    const blueprint = await loadBlueprintFixture("explicit-subtasks");
    const offer = verifyOfferOf(blueprint);

    expect(offer.kind).toBe("offered");
    if (offer.kind === "offered") expect(offer.plan.fingerprint).toBe(blueprint.configuration_fingerprint);
  });

  it("is never offered for a draft preview, which is stored nowhere", async () => {
    expect(verifyOfferOf(await loadBlueprintFixture("draft-preview"))).toEqual({ kind: "draft_preview" });
  });

  it.each(["blocked", "scaffold"])("is not offered for a %s Blueprint, which the server refuses", async (name) => {
    expect(verifyOfferOf(await loadBlueprintFixture(name))).toEqual({ kind: "not_complete", readiness: name });
  });
});

describe("what Verify asks for, read off the Blueprint's tokens", () => {
  it("asks for each start's Grouping Fields, each record's Measurements, and the Subtask kinds started", async () => {
    const plan = await planOf("explicit-subtasks");

    expect(plan.task).toEqual({ altitude: "task", kind: "report_generation", groupingFields: ["environment"] });
    expect(plan.subtasks).toEqual([{ altitude: "subtask", kind: "summarise", groupingFields: ["phase"] }]);
    expect(plan.groupingFields.map((field) => [field.key, field.requiredBy.map((kind) => kind.kind)])).toEqual([
      ["environment", ["report_generation"]],
      ["phase", ["summarise"]],
    ]);
    expect(plan.records.map((record) => record.eventType)).toEqual(["gemini.generate"]);
    const [record] = plan.records;
    expect(record?.measurements.map((measurement) => measurement.code)).toEqual(["candidate_tokens", "prompt_tokens"]);
    // Each Measurement's declared facts come with it, as the Blueprint states them.
    for (const measurement of record?.measurements ?? []) {
      expect(measurement.facts.map(({ argument }) => argument.name)).toEqual([
        `measurements.${measurement.code}.value_type`,
        `measurements.${measurement.code}.unit`,
        `measurements.${measurement.code}.required_for_costing`,
      ]);
    }
    expect(record?.costField).toBeNull();
  });

  it("asks for a supplier cost only where the call reports one, on the field it reports it on", async () => {
    expect((await planOf("reported-cost")).records.map((record) => record.costField)).toEqual([
      "provider_cost_micros",
    ]);
    // #583: a cost generated code reads off the provider's response.
    expect((await planOf("response-cost")).records.map((record) => record.costField)).toEqual([
      "provider_response_cost_micros",
    ]);
    expect((await planOf("calculated-cost")).records.map((record) => record.costField)).toEqual([null]);
  });

  it("sends a cost read off the response on its own field, and never on the caller's", async () => {
    const plan = await planOf("response-cost");
    const samples = blankSamples(plan);
    samples.records = samples.records.map((record) => ({ ...record, providerCost: " 0 " }));

    // A cost of zero is a cost, and is sent.
    expect(verificationRequestOf(plan, samples).records).toEqual([
      { event_type: "grounded.search", measurements: {}, provider_response_cost_micros: 0 },
    ]);
  });

  // A key's token NAME is encoded; its VALUE is the key. A key read back out
  // of a name would send `per%2Ecent%25` for a Measurement named `per.cent%`.
  it("reads each Measurement's key off its key token, never out of a token's name", async () => {
    const blueprint = await loadBlueprintFixture("odd-names");
    const plan = await planOf("odd-names");
    const declared = blueprint.calls.flatMap((call) =>
      call.arguments.flatMap((argument) =>
        argument.name === "measurements" && typeof argument.value === "string" ? [argument.value] : [],
      ),
    );

    expect(plan.records[0]?.measurements.map((measurement) => measurement.code)).toEqual(declared);
    expect(declared).toContain("per.cent%");
  });
});

describe("the request the samples make", () => {
  // ⚠ THE PAGE CAN SEND EXACTLY WHAT THE PLATFORM VERIFIED. Each committed
  // request the page could make is rebuilt from the samples a developer would
  // type, and must be the same request — which is also what lets the mock
  // answer it.
  it("rebuilds every committed request a page can make, exactly", async () => {
    const rebuilt: string[] = [];
    for (const fixture of await committed()) {
      if (fixture.kind !== "answered" || fixture.blueprint === null) continue;
      expect(BLUEPRINT_FIXTURE_NAMES).toContain(fixture.blueprint);
      const plan = await planOf(fixture.blueprint);
      const request = verificationRequestOf(plan, samplesFor(plan, fixture.request));
      if (fixture.name === "calculated-cost-refused-recording") {
        // The one committed request no page can make: a supplier cost on a
        // call that reports none. The page never sends it.
        expect(request.records.every((record) => record.provider_cost_micros === undefined)).toBe(true);
        continue;
      }
      expect(verificationKey(plan.fingerprint, request), fixture.name).toBe(
        verificationKey(fixture.fingerprint, fixture.request),
      );
      rebuilt.push(fixture.name);
    }
    expect(rebuilt.sort()).toEqual([
      "calculated-cost",
      "calculated-cost-without-required-measurements",
      "direct-task-events-partial",
      "explicit-subtasks",
      "reported-cost",
      "response-cost",
    ]);
  });

  // ⚠ #559'S REGRESSION TEST. The server drops an unknown body key silently
  // (#505): the test-event form posted one on every send for months. Held to
  // the committed contract the console is built from, not to a list here.
  it("posts only fields the Verify request publishes", async () => {
    const requests = await Promise.all(
      ["reported-cost", "response-cost", "explicit-subtasks"].map(async (name) => {
        const plan = await planOf(name);
        const fixture = await loadVerificationFixture(name);
        return verificationRequestOf(plan, samplesFor(plan, fixture.request));
      }),
    );
    const request = publishedProperties("IntegrationBlueprintVerificationIn");
    const record = publishedProperties("IntegrationBlueprintVerificationRecordIn");
    const sent = new Set(requests.flatMap((body) => body.records.flatMap((each) => Object.keys(each))));

    for (const body of requests) {
      for (const key of Object.keys(body)) expect(request).toContain(key);
    }
    for (const key of sent) expect(record).toContain(key);
    // Not vacuous: between them the three send every field a record can carry.
    expect([...sent].sort()).toEqual(record.sort());
    expect([...sent].sort()).toEqual([
      "event_type", "measurements", "provider_cost_micros", "provider_response_cost_micros", "subtask_type",
    ]);
  });

  it("sends nothing for a blank sample, and trims what it sends", async () => {
    const plan = await planOf("calculated-cost");
    const samples = blankSamples(plan);
    samples.groupingFields = [" staging "];
    samples.records = samples.records.map((record) => ({ ...record, measurements: [" 12 ", "", ""] }));

    expect(verificationRequestOf(plan, samples)).toEqual({
      records: [{ event_type: "chat.completion", measurements: { input_tokens: 12 } }],
      grouping_fields: { environment: "staging" },
    });
  });

  it("places a record only under a Subtask kind the Blueprint starts", async () => {
    const plan = await planOf("explicit-subtasks");
    const samples = blankSamples(plan);
    samples.records = samples.records.map((record) => ({ ...record, subtaskType: "never_started" }));

    expect(verificationRequestOf(plan, samples).records[0]?.subtask_type).toBeUndefined();
  });

  it("asks a Subtask kind's Grouping Fields only once an included record is placed under it", async () => {
    const plan = await planOf("explicit-subtasks");
    const samples = blankSamples(plan);
    expect(groupingFieldsAsked(plan, samples)).toEqual([0]);

    samples.records = samples.records.map((record) => ({ ...record, subtaskType: "summarise" }));
    expect(groupingFieldsAsked(plan, samples)).toEqual([0, 1]);

    samples.records = samples.records.map((record) => ({ ...record, included: false }));
    expect(groupingFieldsAsked(plan, samples)).toEqual([0]);
  });

  // ⚠ ASSEMBLED, AND SAYS SO: no committed Blueprint starts two Subtask kinds
  // requiring one field, so the platform's explicit-subtasks Blueprint has its
  // Subtask start repeated under a second kind. A field either kind requires
  // is asked whichever of them a record is placed under.
  it("asks a field two Subtask kinds require whichever of them a record is placed under", async () => {
    const blueprint = await loadBlueprintFixture("explicit-subtasks");
    const subtaskStart = blueprint.calls[1];
    if (subtaskStart === undefined) throw new Error("explicit-subtasks starts a Subtask second");
    const second = {
      ...subtaskStart,
      arguments: subtaskStart.arguments.map((argument) =>
        argument.name === "task_type" ? { ...argument, value: "review" } : argument,
      ),
    };
    const offer = verifyOfferOf({
      ...blueprint,
      calls: [...blueprint.calls.slice(0, 2), second, ...blueprint.calls.slice(2)],
    });
    if (offer.kind !== "offered") throw new Error("still complete");
    const plan = offer.plan;
    expect(plan.groupingFields.map((field) => [field.key, field.requiredBy.map((kind) => kind.kind)])).toEqual([
      ["environment", ["report_generation"]],
      ["phase", ["summarise", "review"]],
    ]);

    const samples = blankSamples(plan);
    samples.records = samples.records.map((record) => ({ ...record, subtaskType: "review" }));
    expect(groupingFieldsAsked(plan, samples)).toEqual([0, 1]);
    samples.groupingFields = ["staging", "draft"];
    expect(verificationRequestOf(plan, samples).grouping_fields).toEqual({ environment: "staging", phase: "draft" });
  });
});

describe("what the form refuses to send", () => {
  it("requires a sample for every Grouping Field the run asks for", async () => {
    const plan = await planOf("explicit-subtasks");
    const samples = blankSamples(plan);
    samples.records = samples.records.map((record) => ({ ...record, subtaskType: "summarise" }));
    samples.groupingFields = ["staging", "  "];

    expect(sampleProblems(plan, samples)).toEqual([
      { path: ["groupingFields", 1], message: GROUPING_FIELD_REQUIRED },
    ]);
  });

  it.each(["1.5", "-1", "1e3", "12 tokens", "9007199254740993"])(
    "refuses %j as a sample the request types as an integer",
    async (sample) => {
      const plan = await planOf("reported-cost");
      const samples = blankSamples(plan);
      samples.records = samples.records.map((record) => ({
        ...record,
        measurements: [sample],
        providerCost: sample,
      }));

      expect(sampleProblems(plan, samples)).toEqual([
        { path: ["records", 0, "measurements", 0], message: WHOLE_NUMBER_REQUIRED },
        { path: ["records", 0, "providerCost"], message: WHOLE_NUMBER_REQUIRED },
      ]);
    },
  );

  it("takes a blank sample, a zero and a large whole number", async () => {
    expect(isWholeNumber("0")).toBe(true);
    expect(isWholeNumber("9007199254740991")).toBe(true);
    const plan = await planOf("reported-cost");

    expect(sampleProblems(plan, blankSamples(plan))).toEqual([]);
  });

  it("refuses to run nothing", async () => {
    const plan = await planOf("reported-cost");
    const samples = blankSamples(plan);
    samples.records = samples.records.map((record) => ({ ...record, included: false }));

    expect(sampleProblems(plan, samples)).toEqual([{ path: ["records"], message: NOTHING_TO_RUN }]);
  });

  it("checks nothing about a record left out", async () => {
    const plan = await planOf("direct-task-events");
    const samples = blankSamples(plan);
    samples.records = samples.records.map((record, index) =>
      index === 0 ? record : { ...record, included: false, measurements: ["not a number"] },
    );

    expect(sampleProblems(plan, samples)).toEqual([]);
  });
});

// ⚠ THE WHOLE-NUMBER RULE IS THE PUBLISHED CONTRACT'S (owner review of #601).
// The form shows each Measurement's declared value type, and asks every sample
// as a whole number; this is what makes that the contract's rule rather than
// the form's. A contract that widens a Measurement value, or a value type the
// registry adds, turns these red — and is the day the form starts validating
// by the declared type.
describe("the whole-number rule follows the published contract, for every declared value type", () => {
  /** The type the committed contract gives one Measurement value on a request schema. */
  function measurementValueType(schemaName: string): unknown {
    const [document] = Object.values(
      import.meta.glob("/src/api/schema.json", { eager: true, import: "default" }),
    );
    const at = (node: unknown, key: string): unknown =>
      typeof node === "object" && node !== null ? Reflect.get(node, key) : undefined;
    let node: unknown = document;
    for (const key of ["components", "schemas", schemaName, "properties", "measurements"]) node = at(node, key);
    // The recording request publishes the map nullable: the map is the member that is an object.
    const members = at(node, "anyOf");
    const map = Array.isArray(members) ? members.find((member) => at(member, "type") === "object") : node;
    return at(at(map, "additionalProperties"), "type");
  }

  it("is what both requests publish: every Measurement value is an integer", () => {
    expect(measurementValueType("RecordUsageRequest")).toBe("integer");
    expect(measurementValueType("IntegrationBlueprintVerificationRecordIn")).toBe("integer");
  });

  it("has been decided for every value type the registry declares", () => {
    expect([...MEASUREMENT_VALUE_TYPE_VALUES]).toEqual(["integer", "decimal"]);
  });

  // ⚠ ASSEMBLED, AND SAYS SO: no committed complete Blueprint declares a
  // decimal Measurement, so the platform's calculated-cost Blueprint has one
  // Measurement's declared type changed. Everything else is the platform's.
  it("asks a Measurement declared decimal for a whole number too", async () => {
    const blueprint = await loadBlueprintFixture("calculated-cost");
    const offer = verifyOfferOf({
      ...blueprint,
      calls: blueprint.calls.map((call) => ({
        ...call,
        arguments: call.arguments.map((argument) =>
          argument.name === "measurements.input_tokens.value_type" ? { ...argument, value: "decimal" } : argument,
        ),
      })),
    });
    if (offer.kind !== "offered") throw new Error("still complete");
    const plan = offer.plan;
    expect(plan.records[0]?.measurements.map((measurement) => [measurement.code, measurement.valueType])).toEqual([
      ["input_tokens", "decimal"],
      ["output_tokens", "integer"],
      ["searches", "integer"],
    ]);

    const samples = blankSamples(plan);
    samples.groupingFields = ["staging"];
    samples.records = samples.records.map((record) => ({ ...record, measurements: ["1.5", "", ""] }));
    expect(sampleProblems(plan, samples)).toEqual([
      { path: ["records", 0, "measurements", 0], message: WHOLE_NUMBER_REQUIRED },
    ]);
    samples.records = samples.records.map((record) => ({ ...record, measurements: ["2", "", ""] }));
    expect(sampleProblems(plan, samples)).toEqual([]);
  });
});

describe("what the answer may be presented as", () => {
  it("presents the platform's verified answer as verified", async () => {
    const answer = await answered("reported-cost");
    expect(answer.verified).toBe(true);
    expect(presentedAsVerified(answer)).toBe(true);
  });

  // ⚠ A PARTIAL RUN IS NEVER PRESENTED AS VERIFIED, WHATEVER A FIELD SAYS.
  // Each case takes the verified answer and changes one thing the whole-
  // Blueprint scope rules out.
  it.each<[string, Partial<BlueprintVerification>]>([
    ["an Event Type left out", { unexercised_event_types: ["search.run"] }],
    ["a Subtask kind left out", { unexercised_subtask_types: ["summarise"] }],
    ["the verdict false", { verified: false }],
  ])("does not present %s as verified", async (_name, change) => {
    const answer = { ...(await answered("reported-cost")), ...change };
    expect(presentedAsVerified(answer)).toBe(false);
  });

  it("does not present a run with a refusal or an incomplete recording as verified", async () => {
    const verified = await answered("reported-cost");
    const refused = await answered("calculated-cost-refused-recording");

    expect(presentedAsVerified({ ...verified, refusal: refused.refusal })).toBe(false);
    expect(
      presentedAsVerified({
        ...verified,
        records: verified.records.map((record) => ({ ...record, complete: false })),
      }),
    ).toBe(false);
  });

  it("says the platform's partial run was not verified", async () => {
    expect(presentedAsVerified(await answered("direct-task-events-partial"))).toBe(false);
  });
});

// ⚠ AN ANSWER IS EVIDENCE ABOUT ONE FINGERPRINT AND ONE EXACT REQUEST (owner
// review of #601). The fingerprint names the configuration; it does not name
// the samples, and the samples change what Verify observes.
describe("which Blueprint and which request an answer belongs to", () => {
  async function sentFor(name: string) {
    const fixture = await loadVerificationFixture(name);
    return { fingerprint: fixture.fingerprint, body: fixture.request };
  }

  it("is the current one only while the Blueprint on screen has the fingerprint it ran against", async () => {
    const sent = await sentFor("reported-cost");
    const other = await loadBlueprintFixture("shell-reported-cost");
    const draft = await loadBlueprintFixture("draft-preview");

    expect(standingOf(sent, await loadBlueprintFixture("reported-cost"), sent.body)).toEqual({ kind: "current" });
    expect(standingOf(sent, other, sent.body)).toEqual({
      kind: "another_blueprint",
      ranAgainst: sent.fingerprint,
      current: other.configuration_fingerprint,
    });
    expect(standingOf(sent, draft, null)).toEqual({
      kind: "another_blueprint",
      ranAgainst: sent.fingerprint,
      current: null,
    });
  });

  // The owner's case: verified with one environment, then the sample edited.
  it.each<[string, (request: BlueprintVerificationRequest) => BlueprintVerificationRequest]>([
    ["a Grouping Field sample", (request) => ({ ...request, grouping_fields: { environment: "production" } })],
    [
      "a Measurement sample",
      (request) => ({
        ...request,
        records: request.records.map((record) => ({ ...record, measurements: { ...record.measurements, input_tokens: 1201 } })),
      }),
    ],
    ["an Event Type left out", (request) => ({ ...request, records: request.records.slice(0, 0) })],
    [
      "a supplier cost read off the response",
      (request) => ({
        ...request,
        records: request.records.map((record) => ({ ...record, provider_response_cost_micros: 4200 })),
      }),
    ],
  ])("is not the current one once %s on screen differs from what was sent", async (_edit, change) => {
    const sent = await sentFor("calculated-cost");
    const blueprint = await loadBlueprintFixture("calculated-cost");

    expect(standingOf(sent, blueprint, change(sent.body))).toEqual({ kind: "another_request" });
  });

  it("is not the current one where the Blueprint on screen offers no request at all", async () => {
    const sent = await sentFor("calculated-cost");

    expect(standingOf(sent, await loadBlueprintFixture("calculated-cost"), null)).toEqual({ kind: "another_request" });
  });

  it("is the current one for the same request spelled in another order", async () => {
    const sent = await sentFor("explicit-subtasks");
    const reordered = {
      grouping_fields: { phase: "draft", environment: "staging" },
      records: sent.body.records.map((record) => ({
        subtask_type: record.subtask_type,
        measurements: { candidate_tokens: 250, prompt_tokens: 900 },
        event_type: record.event_type,
      })),
    };

    expect(verificationKey(sent.fingerprint, reordered)).toBe(verificationKey(sent.fingerprint, sent.body));
    expect(standingOf(sent, await loadBlueprintFixture("explicit-subtasks"), reordered)).toEqual({ kind: "current" });
  });
});

describe("a refusal is a precondition, read off the platform's own problem", () => {
  it.each([
    ["not-found", { kind: "not_found" }],
    ["event-type-not-available", { kind: "event_type_not_available", eventTypes: ["draft.only"] }],
  ] as const)("reads %s", async (name, expected) => {
    expect(refusalOf(await refusedWith(name))).toEqual(expected);
  });

  it("reads a 409 as a stored Blueprint that is not complete, and a 422 as a request refused", async () => {
    const conflict = await refusedWith("blocked");
    const invalid = await refusedWith("missing-grouping-field-sample");

    expect(refusalOf(conflict)).toEqual({ kind: "not_complete", detail: conflict.detail });
    expect(refusalOf(invalid)).toEqual({ kind: "invalid", detail: invalid.detail });
  });

  it("reads the floor, and leaves anything else a failure — the mock's own answer included", () => {
    const forbidden = new ApiProblem({ status: 403, code: "forbidden", title: "Forbidden" });
    const mock = new ApiProblem({ status: 404, code: "mock_has_no_verification", title: "Not in the mock" });
    const network = new Error("offline");

    expect(refusalOf(forbidden)).toEqual({ kind: "forbidden" });
    expect(refusalOf(mock)).toEqual({ kind: "other", error: mock });
    expect(refusalOf(network)).toEqual({ kind: "other", error: network });
  });
});

// ⚠ THE ONE UNTYPED PART OF A VERIFY ANSWER is a refusal's extension members
// (`ApiProblem.extensions` is `Record<string, unknown>`), so the narrowing is
// tested directly: a page test would pass over a mock that hands back what it
// was given.
describe("the unavailable Event Types a refusal names", () => {
  it("reads the platform's list", async () => {
    expect(unavailableEventTypesOf(await refusedWith("event-type-not-available"))).toEqual(["draft.only"]);
  });

  it.each([
    ["drops a member that is not a key", { event_types: ["a.event", 3, null, "b.event"] }, ["a.event", "b.event"]],
    ["reads a missing list as none", {}, []],
    ["reads a list that is not a list as none", { event_types: "a.event" }, []],
  ] as const)("%s", (_name, extensions, expected) => {
    const problem = new ApiProblem({
      status: 422,
      code: "event_type_not_available",
      title: "Not available",
      extensions: { ...extensions },
    });
    expect(unavailableEventTypesOf(problem)).toEqual(expected);
  });
});
