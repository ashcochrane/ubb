// What the mock answers Verify with: the platform's own answers (#581).
//
// ⚠ NOT ONE IS WRITTEN HERE. `./verifications/*.json` are written by the
// platform — `test_the_renderers_fixtures_are_what_the_platform_answers.py`
// declares each committed Blueprint's configuration again, verifies its
// fingerprint through the route with a pinned request, and holds file ==
// answer. The ids of the records a run made and discarded, and the instants
// it made them at, are new on every run, so each file holds the ids
// renumbered in the order they first appear and every instant as one held
// instant; nothing else in an answer is touched.
//
// ⚠ THE MOCK ANSWERS ONLY THE EXACT REQUEST THE PLATFORM VERIFIED, for the
// fingerprint it verified it against. Any other samples are a request the
// platform never answered, and the mock says so rather than inventing an
// answer — a Verify answer built by hand is a verdict nobody reached.
//
// Loaded lazily: only mock mode ever reads them.

import { COSTING_STATUS_VALUES, PRICING_STATUS_VALUES } from "@/lib/vocabulary";

import type { BlueprintVerification, BlueprintVerificationRequest } from "./types";

const LOADERS = import.meta.glob<unknown>("./verifications/*.json", { import: "default" });

function nameOf(path: string): string {
  return path.slice(path.lastIndexOf("/") + 1).replace(/\.json$/, "");
}

const LOADER_BY_NAME = new Map(Object.entries(LOADERS).map(([path, load]) => [nameOf(path), load]));

/** Every platform-written Verify answer, by its file's name. */
export const VERIFICATION_FIXTURE_NAMES: readonly string[] = [...LOADER_BY_NAME.keys()].sort();

function isRecord(value: unknown): value is object {
  return typeof value === "object" && value !== null;
}

const field = (value: object, name: string): unknown => Reflect.get(value, name);
const isString = (value: unknown): value is string => typeof value === "string";
const isStringList = (value: unknown) => Array.isArray(value) && value.every(isString);
const isOneOf = <T extends string>(values: readonly T[], value: unknown): value is T =>
  values.some((member) => member === value);

/** A recording's acknowledgement: an event id and the two statuses of their closed sets. */
function isAcknowledgement(value: unknown): boolean {
  return (
    value === null ||
    (isRecord(value) &&
      isString(field(value, "event_id")) &&
      isOneOf(COSTING_STATUS_VALUES, field(value, "costing_status")) &&
      isOneOf(PRICING_STATUS_VALUES, field(value, "pricing_status")))
  );
}

/** A unit of work's two acknowledgements, each an answer or nothing. */
function isUnit(value: unknown): boolean {
  if (!isRecord(value) || !isString(field(value, "task_type"))) return false;
  return ["start", "close"].every((name) => {
    const ack = field(value, name) ?? null;
    return ack === null || (isRecord(ack) && isString(field(ack, "task_id")));
  });
}

/** One record of a run: its Event Type, its two answers and its own verdict. */
function isVerificationRecord(value: unknown): boolean {
  return (
    isRecord(value) &&
    isString(field(value, "event_type")) &&
    typeof field(value, "complete") === "boolean" &&
    isStringList(field(value, "missing_required_measurement_keys")) &&
    isAcknowledgement(field(value, "acknowledgement") ?? null) &&
    isAcknowledgement(field(value, "replay") ?? null)
  );
}

/**
 * An answer's shape, checked at the one place a file becomes one — down to
 * each unit and each record, and each acknowledgement's statuses against the
 * closed sets the contract types them by. A JSON import is typed by its
 * contents, so this is what lets the mock hand the page a typed answer without
 * a cast, and what says so if a file ever stops being one. A Pricing Receipt is
 * untyped in the contract too, and is not checked.
 */
export function isVerification(value: unknown): value is BlueprintVerification {
  if (!isRecord(value)) return false;
  const environment = field(value, "environment");
  const subtasks = field(value, "subtasks");
  const records = field(value, "records");
  const refusal = field(value, "refusal") ?? null;
  return (
    isString(field(value, "configuration_fingerprint")) &&
    typeof field(value, "verified") === "boolean" &&
    isStringList(field(value, "unexercised_event_types")) &&
    isStringList(field(value, "unexercised_subtask_types")) &&
    isRecord(environment) &&
    typeof field(environment, "discarded") === "boolean" &&
    isString(field(environment, "customer_external_id")) &&
    isString(field(environment, "rules_effective_at")) &&
    isUnit(field(value, "task")) &&
    Array.isArray(subtasks) &&
    subtasks.every(isUnit) &&
    Array.isArray(records) &&
    records.every(isVerificationRecord) &&
    (refusal === null ||
      (isRecord(refusal) && isString(field(refusal, "operation_id")) && isProblemBody(field(refusal, "problem"))))
  );
}

/** A problem body as the platform sends one: a status, a code and a title at least. */
export function isProblemBody(value: unknown): value is Record<string, unknown> & {
  status: number;
  code: string;
  title: string;
} {
  return (
    isRecord(value) &&
    typeof field(value, "status") === "number" &&
    isString(field(value, "code")) &&
    isString(field(value, "title"))
  );
}

/** The request the platform verified: one or more records, each naming an Event Type. */
function isRequest(value: unknown): value is BlueprintVerificationRequest {
  if (!isRecord(value)) return false;
  const records = field(value, "records");
  return (
    Array.isArray(records) &&
    records.length > 0 &&
    records.every((record: unknown) => isRecord(record) && isString(field(record, "event_type")))
  );
}

/** One platform-written answer: what was asked, and what the platform said. */
export type CommittedVerification =
  | {
      readonly name: string;
      /** The committed Blueprint whose fingerprint was verified; null for one never stored. */
      readonly blueprint: string | null;
      readonly fingerprint: string;
      readonly request: BlueprintVerificationRequest;
      readonly kind: "answered";
      readonly answer: BlueprintVerification;
    }
  | {
      readonly name: string;
      /** The committed Blueprint whose fingerprint was verified; null for one never stored. */
      readonly blueprint: string | null;
      readonly fingerprint: string;
      readonly request: BlueprintVerificationRequest;
      readonly kind: "refused";
      readonly problem: Record<string, unknown> & { status: number; code: string; title: string };
    };

/** One platform-written answer, by name. */
export async function loadVerificationFixture(name: string): Promise<CommittedVerification> {
  const load = LOADER_BY_NAME.get(name);
  if (load === undefined) throw new Error(`no platform-written Verify answer named ${name}`);
  const document = await load();
  if (!isRecord(document)) throw new Error(`${name} is not a Verify answer`);
  const blueprint = field(document, "blueprint") ?? null;
  const fingerprint = field(document, "configuration_fingerprint");
  const request = field(document, "request");
  const status = field(document, "status");
  const answer = field(document, "answer");
  if (!isString(fingerprint) || !isRequest(request) || !(blueprint === null || isString(blueprint))) {
    throw new Error(`${name} names no request`);
  }
  if (status === 200 && isVerification(answer)) {
    return { name, blueprint, fingerprint, request, kind: "answered", answer };
  }
  if (status !== 200 && isProblemBody(answer) && answer.status === status) {
    return { name, blueprint, fingerprint, request, kind: "refused", problem: answer };
  }
  throw new Error(`${name} is not a Verify answer`);
}

/** An object's entries in one order, so equal maps spell the same key. */
function sortedEntries(value: unknown): Array<[string, unknown]> {
  return isRecord(value) ? Object.entries(value).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)) : [];
}

/**
 * One canonical spelling of a request for a fingerprint, so requests the
 * server reads alike are one key: a map's order is not part of it, a blank
 * map is no map, and an absent optional field is null — the order of the
 * records is, because the run takes them in order.
 */
export function verificationKey(fingerprint: string, request: BlueprintVerificationRequest): string {
  return JSON.stringify([
    fingerprint,
    request.records.map((record) => [
      record.event_type,
      sortedEntries(record.measurements),
      record.provider_cost_micros ?? null,
      record.subtask_type ?? null,
    ]),
    sortedEntries(request.grouping_fields),
  ]);
}

/** Every platform-written answer, by the request it answers. */
export async function mockVerifications(): Promise<Map<string, CommittedVerification>> {
  const answers = new Map<string, CommittedVerification>();
  for (const name of VERIFICATION_FIXTURE_NAMES) {
    const committed = await loadVerificationFixture(name);
    const key = verificationKey(committed.fingerprint, committed.request);
    if (answers.has(key)) throw new Error(`two platform-written answers to one request: ${key}`);
    answers.set(key, committed);
  }
  return answers;
}
