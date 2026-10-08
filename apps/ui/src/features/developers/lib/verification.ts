// Verifying the Blueprint on the Code Builder page (#581).
//
// ⚠ WHAT VERIFY ASKS FOR IS READ OFF THE BLUEPRINT'S TOKENS, NEVER RE-DERIVED.
// A record is one per record call; its Measurements are that call's
// `measurements` key tokens; a supplier cost is asked only where the call
// carries a runtime token for one — `provider_cost_micros` for the caller's
// own figure, `provider_response_cost_micros` for one generated code reads off
// the provider's response (#583) — and is sent on that same field, already in
// micros; a currency is asked only where the call binds `currency` at run time
// — read off the provider's response — and is sent as the event's currency
// (owner review of #608); a Subtask kind is chosen only
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
import {
  MEASUREMENT_VALUE_TYPE_VALUES,
  type IntegrationReadiness,
  type MeasurementValueType,
} from "@/lib/vocabulary";

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
  /** The value type it is declared with, where the Blueprint states one the registry knows. */
  readonly valueType: MeasurementValueType | null;
}

/** One record call: the Event Type it records and what a sample of it needs. */
export interface RecordSample {
  readonly eventType: string;
  readonly measurements: readonly MeasurementSample[];
  /**
   * The field the call reports a supplier cost on, where it reports one: the
   * caller's own figure's, or the one for a figure generated code reads off
   * the provider's response (#570, #583). Each field says where its figure
   * came from, so a sample is sent on the call's own and never the other.
   */
  readonly costField: SupplierCostField | null;
  /**
   * Whether the call binds `currency` at run time — read off the provider's
   * response beside the cost (#583). Then the event's currency is a value the
   * tenant's code passes, so it is a sample here and never one made up: not
   * the tenant's own, which generated code would not send (owner review of
   * #608). A pinned currency is the Blueprint's, and asks for none.
   */
  readonly readsCurrency: boolean;
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

/** The two request fields a supplier's reported cost travels on: one for a
 * figure the caller supplies, one for a figure read off the provider's
 * response. */
export const SUPPLIER_COST_FIELDS = [
  "provider_cost_micros",
  "provider_response_cost_micros",
] as const satisfies readonly (keyof BlueprintVerificationRecordRequest)[];

export type SupplierCostField = (typeof SUPPLIER_COST_FIELDS)[number];

function isSupplierCostField(field: string): field is SupplierCostField {
  return (SUPPLIER_COST_FIELDS as readonly string[]).includes(field);
}

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
    measurements: keysUnder(call, "measurements").map((code) => {
      const declared = facts.filter(
        ({ place }) =>
          place.kind === "fact" &&
          place.field === "measurements" &&
          place.key === code &&
          MEASUREMENT_FACTS.includes(place.element),
      );
      const valueType = declared.find(({ place }) => place.kind === "fact" && place.element === "value_type")
        ?.argument.value;
      return {
        code,
        facts: declared,
        valueType: MEASUREMENT_VALUE_TYPE_VALUES.find((known) => known === valueType) ?? null,
      };
    }),
    costField:
      facts.flatMap(({ argument, place }) =>
        place.kind === "field" &&
        isSupplierCostField(place.field) &&
        argument.binding_class === "runtime_bound"
          ? [place.field]
          : [],
      )[0] ?? null,
    readsCurrency: facts.some(
      ({ argument, place }) =>
        place.kind === "field" && place.field === "currency" && argument.binding_class === "runtime_bound",
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
  /** Whole micros, already converted; "" sends none. Asked only where the
   * call reports a cost, and sent on the field it reports it on. */
  providerCost: string;
  /** The currency code the call reads off the response; asked, and
   * required, only where it does, and sent as the event's currency. */
  currency: string;
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
      currency: "",
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

/**
 * ⚠ EVERY MEASUREMENT SAMPLE IS A WHOLE NUMBER, WHATEVER ITS DECLARED VALUE
 * TYPE — because the call accepts nothing else, not because this form decided
 * it (owner review of #601). The registry's `measurement_value_type` has two
 * values, and a `decimal` Measurement may hold a fraction in the platform's
 * model; but the published recording request (`RecordUsageRequest`) and
 * Verify's record (`IntegrationBlueprintVerificationRecordIn`) both type every
 * Measurement value as an integer, and the generated Shell file refuses a
 * quantity that is not whole. What the wire may carry for a `decimal`
 * Measurement is the platform's to widen, and `verification.test.ts` holds
 * this rule to the committed contract and to the registry's value set: a
 * contract that widens the value, or a value type the registry adds, is a red
 * test there rather than a form that drifted from either.
 */
export const DECIMAL_SENT_WHOLE =
  "Declared decimal, but the recording request carries whole numbers only; leave it blank to send none.";

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
    const currency = typed.currency.trim();
    const under = placedUnder(plan, typed);
    return [
      {
        event_type: record.eventType,
        measurements,
        ...(record.costField !== null && cost !== "" && { [record.costField]: Number(cost) }),
        ...(record.readsCurrency && currency !== "" && { currency }),
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
export const CURRENCY_REQUIRED =
  "A sample currency is required: the call reads its currency off the provider's response at run time, and Verify never makes one up.";
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
    if (record.costField !== null && cost !== "" && !isWholeNumber(cost)) {
      problems.push({ path: ["records", index, "providerCost"], message: WHOLE_NUMBER_REQUIRED });
    }
    // Only that there is one: whether UBB admits it is the recording's own
    // rule, run on the server (#583 D1), and never copied here.
    if (record.readsCurrency && typed.currency.trim() === "") {
      problems.push({ path: ["records", index, "currency"], message: CURRENCY_REQUIRED });
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
          currency: z.string(),
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

/** One Verify as sent: the fingerprint it ran against, and the exact request. */
export interface SentVerification {
  readonly fingerprint: string;
  readonly body: BlueprintVerificationRequest;
}

/** An object's entries in one order, so equal maps spell the same key. */
function sortedEntries(value: unknown): Array<[string, unknown]> {
  return typeof value === "object" && value !== null
    ? Object.entries(value).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
    : [];
}

/**
 * One canonical spelling of a request for a fingerprint, so requests the
 * server reads alike are one key: a map's order is not part of it, a blank
 * map is no map, and an absent optional field is null — the order of the
 * records is, because the run takes them in order. What a Verify answer is
 * evidence about, and what the mock looks an answer up by. Every field a
 * record can carry is in it — each supplier cost field and the currency
 * among them (#583) — so a sample edited after a result can never leave that
 * result standing.
 */
export function verificationKey(fingerprint: string, request: BlueprintVerificationRequest): string {
  return JSON.stringify([
    fingerprint,
    request.records.map((record) => [
      record.event_type,
      sortedEntries(record.measurements),
      record.provider_cost_micros ?? null,
      record.provider_response_cost_micros ?? null,
      record.currency ?? null,
      record.subtask_type ?? null,
    ]),
    sortedEntries(request.grouping_fields),
  ]);
}

export type ResultStanding =
  | { readonly kind: "current" }
  /** The answer, or the refusal, is about a Blueprint not on screen now. */
  | { readonly kind: "another_blueprint"; readonly ranAgainst: string; readonly current: string | null }
  /** Same Blueprint, but the samples on screen are no longer the ones it ran with. */
  | { readonly kind: "another_request" };

/**
 * Whether a Verify answer — or a refusal — speaks for what is on screen now.
 * It is evidence about ONE fingerprint AND ONE exact request (owner review of
 * #601): a Grouping Field sample can select another Cost Rate, a Measurement
 * sample changes what is recorded and costed, and leaving an Event Type out
 * makes the run partial, so an answer survives neither a new fingerprint nor
 * an edited sample. A new fingerprint is the stronger case and is said
 * cause-neutrally; the page re-resolves on focus and on return and does not
 * know what changed. `request` is the request the samples on screen would
 * send, or null where the Blueprint on screen offers no Verify.
 */
export function standingOf(
  sent: SentVerification,
  blueprint: Blueprint,
  request: BlueprintVerificationRequest | null,
): ResultStanding {
  const current = blueprint.configuration_fingerprint ?? null;
  if (current !== sent.fingerprint) {
    return { kind: "another_blueprint", ranAgainst: sent.fingerprint, current };
  }
  return request !== null && verificationKey(current, request) === verificationKey(sent.fingerprint, sent.body)
    ? { kind: "current" }
    : { kind: "another_request" };
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
