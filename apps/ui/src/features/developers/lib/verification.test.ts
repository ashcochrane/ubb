// What Verify asks for, what it sends, and how it reads what comes back
// (#581). Every Blueprint and every answer here is one the platform wrote.

import { describe, expect, it } from "vitest";

import { ApiProblem, toApiProblem } from "@/api/problem";

import { BLUEPRINT_FIXTURE_NAMES, loadBlueprintFixture } from "../api/mock-blueprints";
import {
  loadVerificationFixture,
  VERIFICATION_FIXTURE_NAMES,
  verificationKey,
  type CommittedVerification,
} from "../api/mock-verifications";
import type { BlueprintVerification, BlueprintVerificationRequest } from "../api/types";
import {
  blankSamples,
  GROUPING_FIELD_REQUIRED,
  groupingFieldsAsked,
  isWholeNumber,
  MOCK_HAS_NO_VERIFICATION,
  NOTHING_TO_RUN,
  presentedAsVerified,
  refusalOf,
  sampleProblems,
  standingOf,
  unavailableEventTypesOf,
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
        providerCost: sent?.provider_cost_micros == null ? "" : String(sent.provider_cost_micros),
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
    expect(plan.groupingFields.map((field) => [field.key, field.requiredBy.kind])).toEqual([
      ["environment", "report_generation"],
      ["phase", "summarise"],
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
    expect(record?.reportsCost).toBe(false);
  });

  it("asks for a supplier cost only where the call reports one", async () => {
    expect((await planOf("reported-cost")).records.map((record) => record.reportsCost)).toEqual([true]);
    expect((await planOf("calculated-cost")).records.map((record) => record.reportsCost)).toEqual([false]);
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
    ]);
  });

  // ⚠ #559'S REGRESSION TEST. The server drops an unknown body key silently
  // (#505): the test-event form posted one on every send for months. Held to
  // the committed contract the console is built from, not to a list here.
  it("posts only fields the Verify request publishes", async () => {
    const requests = await Promise.all(
      ["reported-cost", "explicit-subtasks"].map(async (name) => {
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
    // Not vacuous: between them the two send every field a record can carry.
    expect([...sent].sort()).toEqual(["event_type", "measurements", "provider_cost_micros", "subtask_type"]);
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

describe("which Blueprint an answer belongs to", () => {
  it("is the current one only while the Blueprint on screen has the fingerprint it ran against", async () => {
    const blueprint = await loadBlueprintFixture("reported-cost");
    const other = await loadBlueprintFixture("shell-reported-cost");
    const draft = await loadBlueprintFixture("draft-preview");
    const ran = blueprint.configuration_fingerprint ?? "";

    expect(standingOf(ran, blueprint)).toEqual({ kind: "current" });
    expect(standingOf(ran, other)).toEqual({
      kind: "another_blueprint",
      ranAgainst: ran,
      current: other.configuration_fingerprint,
    });
    expect(standingOf(ran, draft)).toEqual({ kind: "another_blueprint", ranAgainst: ran, current: null });
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

  it("reads the floor, the mock's own answer, and anything else", () => {
    const forbidden = new ApiProblem({ status: 403, code: "forbidden", title: "Forbidden" });
    const mock = new ApiProblem({ status: 404, code: MOCK_HAS_NO_VERIFICATION, title: "Not in the mock", detail: "d" });
    const network = new Error("offline");

    expect(refusalOf(forbidden)).toEqual({ kind: "forbidden" });
    expect(refusalOf(mock)).toEqual({ kind: "not_in_the_mock", detail: "d" });
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
