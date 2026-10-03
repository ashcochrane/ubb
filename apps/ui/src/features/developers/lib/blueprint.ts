// Reading an Integration Blueprint for the Code Builder page (#579).
//
// ⚠ THE PAGE NEVER RE-DERIVES WHAT THE BLUEPRINT SAYS. Every fact it shows —
// the provider, the costing method, a Measurement's type, unit and required
// flag, a required Grouping Field, a kind's declared ceiling or `uncapped`,
// the frozen pricing mode — is a token of a call, and each token names the
// declaration it was read from. This module reads tokens as the contract
// describes them (ADR-0015 §3); it resolves nothing, and nothing here decides
// a verdict the server did not state.

import type { OperationId, WebhookEventName } from "@/api/types";
import {
  AMOUNT_REPRESENTATION_LABEL_KEYS,
  COSTING_METHOD_LABEL_KEYS,
  MEASUREMENT_VALUE_TYPE_LABEL_KEYS,
  PRICING_MODE_LABEL_KEYS,
  RESPONSE_SHAPE_REPRESENTATION_LABEL_KEYS,
  SOURCE_SHAPE_ID_LABEL_KEYS,
  UNIT_LABEL_KEYS,
  type IntegrationReadiness,
  type TaskTypeKind,
} from "@/lib/vocabulary";

import type {
  Blueprint,
  BlueprintArgument,
  BlueprintCall,
  BlueprintDiagnostic,
  RecordUsageRequest,
  RemediationRequest,
} from "../api/types";

// ---------------------------------------------------------------------------
// The stages, in order. The page renders one section per stage, keyed on this
// list, so #581 adds its Verify stage by appending one id here — and `tsc`
// then asks for that stage's title and component wherever the page keys on it.

export const CODE_BUILDER_STAGES = ["configure", "blueprint", "generate"] as const;
export type CodeBuilderStage = (typeof CODE_BUILDER_STAGES)[number];

// ---------------------------------------------------------------------------
// Calls

/** The three operations a Blueprint's calls name, held to the contract. */
export const START_TASK = "api_v1_task_endpoints_start_task" satisfies OperationId;
export const RECORD_USAGE = "api_v1_metering_endpoints_record_usage" satisfies OperationId;
export const CLOSE_TASK = "api_v1_task_endpoints_close_task" satisfies OperationId;

export type CallRole = "start_task" | "start_subtask" | "record_usage" | "close_task" | "other";

/**
 * What a call does in the lifecycle. A Subtask is started by the same
 * operation as a Task and told apart by naming its parent — the renderer's
 * rule too.
 */
export function roleOf(call: BlueprintCall): CallRole {
  if (call.operation_id === START_TASK) {
    return call.arguments.some((argument) => argument.name === "parent_task_id")
      ? "start_subtask"
      : "start_task";
  }
  if (call.operation_id === RECORD_USAGE) return "record_usage";
  if (call.operation_id === CLOSE_TASK) return "close_task";
  return "other";
}

/**
 * The declared object a call is about — the kind a start names, the Event Type
 * a record names — or null where it names none (nothing selected, or not
 * declared: the token is there, unconfigured).
 */
export function subjectOf(call: BlueprintCall): string | null {
  const field = roleOf(call) === "record_usage" ? "event_type" : "task_type";
  const token = call.arguments.find((argument) => argument.name === field);
  return token?.configured === true && typeof token.value === "string" ? token.value : null;
}

// ---------------------------------------------------------------------------
// Tokens

/**
 * The request fields that hold an object of declared keys. For these, a
 * token named for the field is ONE KEY, `<field>.<key>` is the value under
 * it, and a fact needs a third segment; for every other field the second
 * segment is already the fact. Typed against the recording request, so a
 * field the contract renames stops compiling here.
 */
export const KEYED_FIELDS = ["grouping_fields", "measurements"] as const satisfies ReadonlyArray<
  keyof RecordUsageRequest
>;

function isKeyed(field: string): boolean {
  return KEYED_FIELDS.some((keyed) => keyed === field);
}

/** Where a token sits, by the convention its name follows. */
export type TokenPlace =
  | { readonly kind: "field"; readonly field: string }
  | { readonly kind: "keyed_value"; readonly field: string; readonly key: string | null }
  | {
      readonly kind: "fact";
      readonly field: string;
      readonly element: string;
      readonly key: string | null;
    };

/**
 * Each token's place, in the call's order.
 *
 * A key is never decoded out of a name. A key's own token carries the key
 * unencoded in `value`, and every token named under that key follows it
 * directly (the contract says so), so the key of `<field>.<key>…` is the
 * value of the nearest `<field>` token before it.
 */
export function placesOf(call: BlueprintCall): TokenPlace[] {
  const lastKey = new Map<string, string>();
  return call.arguments.map((argument): TokenPlace => {
    const segments = argument.name.split(".");
    const field = segments[0] ?? argument.name;
    if (segments.length === 1) {
      if (isKeyed(field) && typeof argument.value === "string") {
        lastKey.set(field, argument.value);
      }
      return { kind: "field", field };
    }
    const key = isKeyed(field) ? (lastKey.get(field) ?? null) : null;
    if (isKeyed(field) && segments.length === 2) {
      return { kind: "keyed_value", field, key };
    }
    return { kind: "fact", field, element: segments[segments.length - 1] ?? "", key };
  });
}

/** How the page shows one token's value. */
export type Shown =
  /** A credential: never a value, only the variable that holds it. */
  | { readonly kind: "secret"; readonly variable: string }
  /** Supplied when the code runs, under this parameter's name. */
  | { readonly kind: "parameter"; readonly parameter: string }
  /** Known to UBB once it is declared; not declared yet. */
  | { readonly kind: "unconfigured" }
  /** A value of a registry concept, worded by the catalogue. */
  | {
      readonly kind: "concept";
      readonly labelKeys: Readonly<Record<string, string>>;
      readonly value: string;
    }
  /** A ceiling's figure, in micros of the workspace currency. */
  | { readonly kind: "money"; readonly micros: number }
  /** A capped kind that declares no figure of its own. */
  | { readonly kind: "no_ceiling_declared" }
  /** A path into a supplier's response, one segment at a time. */
  | { readonly kind: "path"; readonly segments: readonly string[] }
  /** Anything else, as the tenant declared it or as the document holds it. */
  | { readonly kind: "text"; readonly text: string };

/** The declared facts whose values are a registry concept's. */
const CONCEPT_OF_FACT: Readonly<Record<string, Readonly<Record<string, string>>>> = {
  pricing_mode: PRICING_MODE_LABEL_KEYS,
  costing_method: COSTING_METHOD_LABEL_KEYS,
  value_type: MEASUREMENT_VALUE_TYPE_LABEL_KEYS,
  unit: UNIT_LABEL_KEYS,
  amount_representation: AMOUNT_REPRESENTATION_LABEL_KEYS,
  source_shape_id: SOURCE_SHAPE_ID_LABEL_KEYS,
  response_shape_representation: RESPONSE_SHAPE_REPRESENTATION_LABEL_KEYS,
};

/** The declared facts that are a yes or a no, and how each reads. */
const FLAG_WORDING: Readonly<Record<string, { readonly yes: string; readonly no: string }>> = {
  uncapped: { yes: "Uncapped", no: "Capped" },
  required_for_costing: {
    yes: "Required for a complete cost",
    no: "Not required for a complete cost",
  },
};

/** The fact naming a kind's declared ceiling, in micros. */
export const CEILING_FACT = "task_cogs_ceiling_micros";

function asText(value: unknown): string {
  if (typeof value === "string") return value;
  return JSON.stringify(value) ?? "";
}

function isSegmentList(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((segment) => typeof segment === "string");
}

/**
 * How one token's value is shown, decided by its binding class first and by
 * the fact it states second. A value whose shape is not the one its fact
 * declares is shown as the document holds it — never coerced into a word or
 * a figure it does not say.
 */
export function shownValue(argument: BlueprintArgument, place: TokenPlace): Shown {
  if (argument.binding_class === "secret_reference") {
    return { kind: "secret", variable: argument.environment_variable ?? "" };
  }
  if (argument.binding_class === "runtime_bound") {
    return { kind: "parameter", parameter: argument.parameter_name ?? "" };
  }
  if (!argument.configured) return { kind: "unconfigured" };
  const value: unknown = argument.value;
  if (place.kind === "fact") {
    const concept = CONCEPT_OF_FACT[place.element];
    if (concept !== undefined && typeof value === "string") {
      return { kind: "concept", labelKeys: concept, value };
    }
    const flag = FLAG_WORDING[place.element];
    if (flag !== undefined && typeof value === "boolean") {
      return { kind: "text", text: value ? flag.yes : flag.no };
    }
    if (place.element === CEILING_FACT) {
      if (value === null) return { kind: "no_ceiling_declared" };
      if (typeof value === "number") return { kind: "money", micros: value };
    }
    if (isSegmentList(value)) return { kind: "path", segments: value };
  }
  return { kind: "text", text: asText(value) };
}

// ---------------------------------------------------------------------------
// Where the round trip goes

/** A console screen that owns something the page points at (§11). */
export type ConsoleScreen =
  | { readonly to: "/tasks/kinds/$key"; readonly params: { readonly key: string } }
  | { readonly to: "/tasks" }
  | { readonly to: "/pricing" }
  | { readonly to: "/webhooks" };

function isKindOfWork(objectKind: string | undefined): boolean {
  return objectKind === "task_type" || objectKind === "subtask_type";
}

/**
 * The screen a fact can be changed on, where the console has one: a kind of
 * work's own page for its key; the workspace defaults on `/tasks` for a
 * capped kind declaring no ceiling of its own; the Cost Rates on `/pricing`
 * for an Event Type whose cost is calculated from them. Event Types,
 * Measurements, mappings, providers and Grouping Fields have no console
 * screen — a problem with one of those is a diagnostic, and its fix a request.
 */
export function screenFor(argument: BlueprintArgument, place: TokenPlace): ConsoleScreen | null {
  if (argument.binding_class !== "platform_known" || !argument.configured) return null;
  const provenance = argument.provenance;
  if (
    place.kind === "field" &&
    place.field === "task_type" &&
    isKindOfWork(provenance?.object_kind) &&
    typeof argument.value === "string"
  ) {
    return { to: "/tasks/kinds/$key", params: { key: argument.value } };
  }
  if (place.kind === "fact" && place.element === CEILING_FACT && argument.value === null) {
    return { to: "/tasks" };
  }
  if (place.kind === "fact" && place.element === "costing_method" && argument.value === "calculated") {
    return { to: "/pricing" };
  }
  return null;
}

/** What answers a diagnostic. */
export type Fix =
  /** The console has a screen for the object. */
  | { readonly kind: "screen"; readonly screen: ConsoleScreen }
  /** It has none: the request that fixes it, to copy. The page never sends it. */
  | { readonly kind: "request"; readonly request: RemediationRequest }
  /** Nothing is selected: the answer is a choice on this page. */
  | { readonly kind: "select" }
  /** The diagnostic offers nothing to act on. */
  | { readonly kind: "none" };

export function fixFor(diagnostic: BlueprintDiagnostic): Fix {
  const key = diagnostic.key ?? null;
  if (key === null) return { kind: "select" };
  if (isKindOfWork(diagnostic.object_kind)) {
    // A kind that is not declared has no page of its own yet; kinds are
    // declared on Tasks.
    return diagnostic.code === "task_type_not_declared"
      ? { kind: "screen", screen: { to: "/tasks" } }
      : { kind: "screen", screen: { to: "/tasks/kinds/$key", params: { key } } };
  }
  const request = diagnostic.remediation_request ?? null;
  return request === null ? { kind: "none" } : { kind: "request", request };
}

/**
 * A remediation request as text to copy: the method and the route, then the
 * body if the operation takes one. No host and no credential — the request is
 * the server's, carrying nothing of the tenant's beyond the object's key.
 */
export function remediationText(request: RemediationRequest): string {
  const line = `${request.method} ${request.route}`;
  const body = request.body ?? null;
  return body === null ? `${line}\n` : `${line}\n\n${JSON.stringify(body, null, 2)}\n`;
}

/**
 * The operation's entry in the API's own interactive reference, which the
 * platform serves beside the API. The contract groups no operation under a
 * heading of its own, so the reference files every one of them under
 * `default`.
 */
export function apiReferenceUrl(origin: string, operationId: string): string {
  return `${origin}/api/v1/docs#/default/${encodeURIComponent(operationId)}`;
}

// ---------------------------------------------------------------------------
// Webhooks (§14): what a kind's limits can announce when nobody is calling

/**
 * The two terminal announcements at each altitude, held to the contract's
 * `webhooks` section: a renamed event stops compiling here. Killed is a spend
 * stop — the kind's own ceiling, or a customer-wide stop reaching the work;
 * expired is the silence window or the absolute deadline, which no kind can
 * switch off.
 */
export const TERMINAL_STOP_EVENTS = {
  task: { killed: "task.killed", expired: "task.expired" },
  subtask: { killed: "subtask.killed", expired: "subtask.expired" },
} as const satisfies Record<TaskTypeKind, Record<"killed" | "expired", WebhookEventName>>;

export interface KindAnnouncements {
  readonly altitude: TaskTypeKind;
  readonly kind: string;
  /** The kind's declared posture: null where the Blueprint does not state it. */
  readonly uncapped: boolean | null;
  readonly events: { readonly killed: WebhookEventName; readonly expired: WebhookEventName };
}

/** One entry per kind the Blueprint starts. No handler is generated (§14). */
export function announcementsOf(blueprint: Blueprint): KindAnnouncements[] {
  return blueprint.calls.flatMap((call): KindAnnouncements[] => {
    const role = roleOf(call);
    if (role !== "start_task" && role !== "start_subtask") return [];
    const kind = subjectOf(call);
    if (kind === null) return [];
    const altitude: TaskTypeKind = role === "start_subtask" ? "subtask" : "task";
    const uncapped = call.arguments.find((argument) => argument.name === "task_type.uncapped");
    return [
      {
        altitude,
        kind,
        uncapped: typeof uncapped?.value === "boolean" ? uncapped.value : null,
        events: TERMINAL_STOP_EVENTS[altitude],
      },
    ];
  });
}

// ---------------------------------------------------------------------------
// The files a developer holds

export type Staleness =
  | { readonly kind: "nothing_held" }
  | { readonly kind: "current" }
  | { readonly kind: "stale"; readonly held: string; readonly current: string | null };

/**
 * Whether the files last taken from this page still describe the Blueprint
 * now resolved. A draft preview has no fingerprint, so files held never match
 * one.
 */
export function stalenessOf(held: string | undefined, blueprint: Blueprint): Staleness {
  if (held === undefined) return { kind: "nothing_held" };
  const current = blueprint.configuration_fingerprint ?? null;
  return current === held ? { kind: "current" } : { kind: "stale", held, current };
}

/**
 * The copy action's words. Until the verdict is `complete` the code is a
 * scaffold, and the action says so — a label is lost on copy, so the code's
 * own header says it too (#156 §8.4).
 */
export function copyActionLabel(readiness: IntegrationReadiness): string {
  return readiness === "complete" ? "Copy integration" : "Copy scaffold";
}
