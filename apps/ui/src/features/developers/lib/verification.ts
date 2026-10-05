// Verifying the Blueprint on the Code Builder page (#581).
//
// ⚠ WHAT VERIFY ASKS FOR IS READ OFF THE BLUEPRINT'S TOKENS, NEVER RE-DERIVED.
// A record is one per record call; its Measurements are that call's
// `measurements` key tokens; a supplier cost is asked only where the call
// carries a `provider_cost_micros` runtime token; a Subtask kind is chosen only
// among the Subtask starts; a Grouping Field sample is asked for every
// `grouping_fields` key token on the Task start, and on each Subtask start a
// record is placed under. Verify never makes up a value a tenant's code passes
// at run time (owner ruling on #599), so each of those is a sample here.
//
// The server stays authoritative. The form checks only what it can know for
// certain from the Blueprint and the contract — every required Grouping Field
// has a sample, every sample the request types as an integer is a whole number,
// and at least one Event Type runs — and leaves everything else to the 422.

import { z } from "zod";

import { ApiProblem } from "@/api/problem";
import type { IntegrationReadiness } from "@/lib/vocabulary";

import type {
  Blueprint,
  BlueprintArgument,
  BlueprintCall,
  BlueprintVerification,
  BlueprintVerificationRecordRequest,
  BlueprintVerificationRequest,
} from "../api/types";
import { placesOf, roleOf, subjectOf, type TokenPlace } from "./blueprint";

// ---------------------------------------------------------------------------
// Whether Verify is offered

/** A kind of work the run starts, and the Grouping Fields it requires. */
export interface StartedKind {
  readonly altitude: "task" | "subtask";
  readonly kind: string;
  /** Each required Grouping Field's key, as its key token holds it. */
  readonly groupingFields: readonly string[];
}

/** One declared fact about a Measurement, as the Blueprint states it. */
export interface MeasurementFact {
  readonly argument: BlueprintArgument;
  readonly place: TokenPlace;
}

/** A Measurement the record sends, and what its declaration says of it. */
export interface MeasurementSample {
  /** The key, unencoded: the value of the call's `measurements` key token. */
  readonly code: string;
  /** Its value type, unit and whether it is required for a complete cost. */
  readonly facts: readonly MeasurementFact[];
}

/** One record call: the Event Type it records and what a sample of it needs. */
export interface RecordSample {
  readonly eventType: string;
  readonly measurements: readonly MeasurementSample[];
  /** True where the call reports a supplier cost the caller supplies. */
  readonly reportsCost: boolean;
}

/** A Grouping Field a sample may be asked for, and every kind requiring it. */
export interface GroupingFieldSample {
  readonly key: string;
  /** Each kind that requires it — one key can be required by several. */
  readonly requiredBy: readonly StartedKind[];
}

/** Everything Verify asks for, read off one stored, complete Blueprint. */
export interface SamplePlan {
  readonly fingerprint: string;
  readonly task: StartedKind | null;
  readonly subtasks: readonly StartedKind[];
  readonly records: readonly RecordSample[];
  /** The Task's fields first, then each Subtask kind's: each key once, with every kind requiring it. */
  readonly groupingFields: readonly GroupingFieldSample[];
}

export type VerifyOffer =
  /** No fingerprint: stored nowhere, so there is nothing to verify (#567 point 3). */
  | { readonly kind: "draft_preview" }
  /** Stored, and not complete: the server would answer 409. */
  | { readonly kind: "not_complete"; readonly readiness: IntegrationReadiness }
  | { readonly kind: "offered"; readonly plan: SamplePlan };

/** The facts of a Measurement the Verify form shows beside its sample. */
const MEASUREMENT_FACTS = ["value_type", "unit", "required_for_costing"];

/** The request field carrying a supplier's reported cost. */
const REPORTED_COST = "provider_cost_micros" satisfies keyof BlueprintVerificationRecordRequest;

function tokens(call: BlueprintCall): Array<{ argument: BlueprintArgument; place: TokenPlace }> {
  const places = placesOf(call);
  return call.arguments.flatMap((argument, index) => {
    const place = places[index];
    return place === undefined ? [] : [{ argument, place }];
  });
}

/** The keys a call's key tokens name under one keyed field, in the call's order. */
function keysUnder(call: BlueprintCall, field: string): string[] {
  return tokens(call).flatMap(({ argument, place }) =>
    place.kind === "field" && place.field === field && typeof argument.value === "string"
      ? [argument.value]
      : [],
  );
}

function startedKind(call: BlueprintCall, altitude: "task" | "subtask"): StartedKind | null {
  const kind = subjectOf(call);
  return kind === null ? null : { altitude, kind, groupingFields: keysUnder(call, "grouping_fields") };
}

function recordSample(call: BlueprintCall): RecordSample | null {
  const eventType = subjectOf(call);
  if (eventType === null) return null;
  const facts = tokens(call);
  return {
    eventType,
    measurements: keysUnder(call, "measurements").map((code) => ({
      code,
      facts: facts.filter(
        ({ place }) =>
          place.kind === "fact" &&
          place.field === "measurements" &&
          place.key === code &&
          MEASUREMENT_FACTS.includes(place.element),
      ),
    })),
    reportsCost: facts.some(
      ({ argument, place }) =>
        place.kind === "field" &&
        place.field === REPORTED_COST &&
        argument.binding_class === "runtime_bound",
    ),
  };
}

/** What Verify asks for, read off the Blueprint's calls. */
export function samplePlanOf(blueprint: Blueprint, fingerprint: string): SamplePlan {
  let task: StartedKind | null = null;
  const subtasks: StartedKind[] = [];
  const records: RecordSample[] = [];
  for (const call of blueprint.calls) {
    const role = roleOf(call);
    if (role === "start_task" && task === null) task = startedKind(call, "task");
    if (role === "start_subtask") {
      const started = startedKind(call, "subtask");
      if (started !== null && !subtasks.some((known) => known.kind === started.kind)) {
        subtasks.push(started);
      }
    }
    if (role === "record_usage") {
      const record = recordSample(call);
      if (record !== null) records.push(record);
    }
  }
  const requiredBy = new Map<string, StartedKind[]>();
  for (const kind of [...(task === null ? [] : [task]), ...subtasks]) {
    for (const key of kind.groupingFields) {
      requiredBy.set(key, [...(requiredBy.get(key) ?? []), kind]);
    }
  }
  const groupingFields = [...requiredBy].map(([key, kinds]) => ({ key, requiredBy: kinds }));
  return { fingerprint, task, subtasks, records, groupingFields };
}

/**
 * Whether the page offers Verify for the Blueprint on screen: only for a
 * stored one whose verdict is `complete`. A draft preview has no fingerprint;
 * a stored Blueprint that is not complete is the server's 409.
 */
export function verifyOfferOf(blueprint: Blueprint): VerifyOffer {
  const fingerprint = blueprint.configuration_fingerprint ?? null;
  if (fingerprint === null) return { kind: "draft_preview" };
  if (blueprint.readiness !== "complete") {
    return { kind: "not_complete", readiness: blueprint.readiness };
  }
  return { kind: "offered", plan: samplePlanOf(blueprint, fingerprint) };
}

// ---------------------------------------------------------------------------
// The samples, and the request they make

/** One record's samples, as typed. Positional against the plan's record. */
export interface RecordSampleValues {
  included: boolean;
  /** A Subtask kind the record is placed under; "" places it under the Task. */
  subtaskType: string;
  /** Positional against the record's Measurements; "" sends none. */
  measurements: string[];
  /** Whole micros; "" sends none. Asked only where the call reports a cost. */
  providerCost: string;
}

/**
 * Everything the developer typed. Positional, never keyed by a declared key:
 * a tenant's key may hold a `.`, which a form's field path would split.
 */
export interface SampleValues {
  /** Positional against the plan's Grouping Fields. */
  groupingFields: string[];
  records: RecordSampleValues[];
}

/** Nothing typed yet: every Event Type included, every record under the Task. */
export function blankSamples(plan: SamplePlan): SampleValues {
  return {
    groupingFields: plan.groupingFields.map(() => ""),
    records: plan.records.map((record) => ({
      included: true,
      subtaskType: "",
      measurements: record.measurements.map(() => ""),
      providerCost: "",
    })),
  };
}

/** The Subtask kind a record is placed under, if it is one the Blueprint starts. */
function placedUnder(plan: SamplePlan, values: RecordSampleValues): string | null {
  return plan.subtasks.some((kind) => kind.kind === values.subtaskType) ? values.subtaskType : null;
}

/**
 * The Grouping Fields this run needs a sample for, by position: the Task
 * kind's, and those of each Subtask kind an included record is placed under.
 * A Subtask kind no record is placed under is never started, and needs none;
 * a field two kinds require is asked as soon as either is started.
 */
export function groupingFieldsAsked(plan: SamplePlan, values: SampleValues): number[] {
  const started = new Set(
    plan.records.flatMap((_, index) => {
      const record = values.records[index];
      const kind = record?.included === true ? placedUnder(plan, record) : null;
      return kind === null ? [] : [kind];
    }),
  );
  return plan.groupingFields.flatMap((field, index) =>
    field.requiredBy.some((kind) => kind.altitude === "task" || started.has(kind.kind)) ? [index] : [],
  );
}

const WHOLE_NUMBER = /^\d+$/;

/** A whole number the request can carry: digits only, and exactly representable. */
export function isWholeNumber(text: string): boolean {
  return WHOLE_NUMBER.test(text) && Number.isSafeInteger(Number(text));
}

/**
 * The Verify request for these samples, held to the contract's request
 * schema. Only included records are sent; a blank sample sends nothing; a
 * supplier cost only where the call reports one; a Subtask kind only where
 * the Blueprint starts it; a Grouping Field sample only where the run asks.
 */
export function verificationRequestOf(
  plan: SamplePlan,
  values: SampleValues,
): BlueprintVerificationRequest {
  const records = plan.records.flatMap((record, index): BlueprintVerificationRecordRequest[] => {
    const typed = values.records[index];
    if (typed === undefined || !typed.included) return [];
    const measurements: Record<string, number> = {};
    record.measurements.forEach((measurement, position) => {
      const sample = (typed.measurements[position] ?? "").trim();
      if (sample !== "") measurements[measurement.code] = Number(sample);
    });
    const cost = typed.providerCost.trim();
    const under = placedUnder(plan, typed);
    return [
      {
        event_type: record.eventType,
        measurements,
        ...(record.reportsCost && cost !== "" && { provider_cost_micros: Number(cost) }),
        ...(under !== null && { subtask_type: under }),
      },
    ];
  });
  const groupingFields: Record<string, string> = {};
  for (const index of groupingFieldsAsked(plan, values)) {
    const field = plan.groupingFields[index];
    if (field !== undefined) groupingFields[field.key] = (values.groupingFields[index] ?? "").trim();
  }
  return { records, grouping_fields: groupingFields };
}

/** One thing the form refuses to send, at the field it is about. */
export interface SampleProblem {
  readonly path: Array<string | number>;
  readonly message: string;
}

export const GROUPING_FIELD_REQUIRED =
  "A sample value is required: the kind of work this run starts requires it, and Verify never makes one up.";
export const WHOLE_NUMBER_REQUIRED = "A whole number: the request carries whole numbers only.";
export const NOTHING_TO_RUN = "Include at least one Event Type.";

/** What the form checks before sending. Everything else is the server's to refuse. */
export function sampleProblems(plan: SamplePlan, values: SampleValues): SampleProblem[] {
  const problems: SampleProblem[] = [];
  for (const index of groupingFieldsAsked(plan, values)) {
    if ((values.groupingFields[index] ?? "").trim() === "") {
      problems.push({ path: ["groupingFields", index], message: GROUPING_FIELD_REQUIRED });
    }
  }
  plan.records.forEach((record, index) => {
    const typed = values.records[index];
    if (typed === undefined || !typed.included) return;
    record.measurements.forEach((_, position) => {
      const sample = (typed.measurements[position] ?? "").trim();
      if (sample !== "" && !isWholeNumber(sample)) {
        problems.push({ path: ["records", index, "measurements", position], message: WHOLE_NUMBER_REQUIRED });
      }
    });
    const cost = typed.providerCost.trim();
    if (record.reportsCost && cost !== "" && !isWholeNumber(cost)) {
      problems.push({ path: ["records", index, "providerCost"], message: WHOLE_NUMBER_REQUIRED });
    }
  });
  if (!values.records.some((record) => record.included)) {
    problems.push({ path: ["records"], message: NOTHING_TO_RUN });
  }
  return problems;
}

/** The form's checks as a schema for its resolver: `sampleProblems`, at each field's path. */
export function sampleFormSchema(plan: SamplePlan) {
  return z
    .object({
      groupingFields: z.array(z.string()),
      records: z.array(
        z.object({
          included: z.boolean(),
          subtaskType: z.string(),
          measurements: z.array(z.string()),
          providerCost: z.string(),
        }),
      ),
    })
    .superRefine((values, context) => {
      for (const problem of sampleProblems(plan, values)) {
        context.addIssue({ code: "custom", path: problem.path, message: problem.message });
      }
    });
}

// ---------------------------------------------------------------------------
// What came back

/**
 * Whether the page may say "verified". Only where the server says so AND
 * nothing it answered contradicts the whole-Blueprint scope: no refusal,
 * nothing left out, every recording complete. A partial run is never
 * presented as verified, whatever a field says.
 */
export function presentedAsVerified(result: BlueprintVerification): boolean {
  return (
    result.verified &&
    (result.refusal ?? null) === null &&
    result.unexercised_event_types.length === 0 &&
    result.unexercised_subtask_types.length === 0 &&
    result.records.every((record) => record.complete)
  );
}

export type ResultStanding =
  | { readonly kind: "current" }
  /** The answer, or the refusal, is about a Blueprint not on screen now. */
  | { readonly kind: "another_blueprint"; readonly ranAgainst: string; readonly current: string | null };

/**
 * Whether a Verify answer speaks for the Blueprint now on screen. It belongs
 * to the fingerprint it ran against; the page re-resolves on focus and on
 * return, and a Blueprint that now resolves to another fingerprint is not the
 * one that was verified — whatever changed, which the page does not know.
 */
export function standingOf(ranAgainst: string, blueprint: Blueprint): ResultStanding {
  const current = blueprint.configuration_fingerprint ?? null;
  return current === ranAgainst ? { kind: "current" } : { kind: "another_blueprint", ranAgainst, current };
}

/** Why Verify was refused before anything ran. */
export type VerifyRefusal =
  /** Unknown, or pruned 30 days after it was last resolved. */
  | { readonly kind: "not_found" }
  /** An Event Type the request claims that the stored Blueprint does not publish. */
  | { readonly kind: "event_type_not_available"; readonly eventTypes: readonly string[] }
  /** The stored Blueprint is not complete. */
  | { readonly kind: "not_complete"; readonly detail: string | null }
  | { readonly kind: "invalid"; readonly detail: string | null }
  | { readonly kind: "forbidden" }
  /** Anything else — including mock mode's own "Not in the mock" — is a failure, not a precondition. */
  | { readonly kind: "other"; readonly error: unknown };

/**
 * The Event Types a refusal names as unavailable. The problem's extension
 * members are untyped (`ApiProblem.extensions`), so the list is narrowed here
 * and nowhere else: a key that is not a string is dropped, and a missing list
 * is an empty one.
 */
export function unavailableEventTypesOf(problem: ApiProblem): string[] {
  const listed: unknown = problem.extensions["event_types"];
  return Array.isArray(listed) ? listed.filter((key): key is string => typeof key === "string") : [];
}

/** A refusal is a precondition the request did not meet — never a mapping failure. */
export function refusalOf(error: unknown): VerifyRefusal {
  if (!(error instanceof ApiProblem)) return { kind: "other", error };
  switch (error.code) {
    case "not_found":
      return { kind: "not_found" };
    case "event_type_not_available":
      return { kind: "event_type_not_available", eventTypes: unavailableEventTypesOf(error) };
    case "conflict":
      return { kind: "not_complete", detail: error.detail };
    case "validation_error":
      return { kind: "invalid", detail: error.detail };
    case "forbidden":
      return { kind: "forbidden" };
    default:
      return { kind: "other", error };
  }
}
