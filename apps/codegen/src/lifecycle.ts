/**
 * A Blueprint read as the lifecycle every target renders: one start of the
 * work, the starts of work contained in it, the records and the closes.
 *
 * Target-neutral. A Blueprint names real v1 operations; which of them a call
 * is, and the few request fields a lifecycle is built around, are the same
 * whatever file is written. What each target DOES with an operation — an SDK
 * method, or a route and a body — is that target's own.
 */
import { refuse, type ResolvedIntegrationBlueprint } from "./blueprint.ts";
import { ENVIRONMENT } from "./catalogue.ts";
import {
  literalOf,
  parameters,
  readCall,
  type Call,
  type SecretReference,
  type Token,
} from "./tokens.ts";

/** The operations a lifecycle is made of. */
export const OPERATION_IDS = {
  start: "api_v1_task_endpoints_start_task",
  record: "api_v1_metering_endpoints_record_usage",
  close: "api_v1_task_endpoints_close_task",
} as const;

/**
 * The request fields a target knows by name, because a lifecycle is built
 * around them: the one that says work is contained in other work, the two
 * whose literal a generated function is named for, and the one a cost is
 * denominated in.
 */
export const FIELD = {
  parent: "parent_task_id",
  kindOfWork: "task_type",
  eventType: "event_type",
  currency: "currency",
} as const;

/** The declared facts a target may act on, by the last segment of their name. */
export const FACT = {
  sourcePath: "source_path",
  responseRepresentation: "response_shape_representation",
  amountRepresentation: "amount_representation",
  pricingMode: "pricing_mode",
  valueType: "value_type",
} as const;

/** The document without its calls: what a file's header states. */
export type Header = Omit<ResolvedIntegrationBlueprint, "calls">;

export interface Lifecycle {
  /** Everything of the document but its calls, which are read into `calls`:
   * no writer is handed a raw token. */
  readonly header: Header;
  readonly calls: readonly Call[];
  readonly credential: Token<SecretReference>;
  /** The start of the work itself. */
  readonly start: Call;
  /** The starts of work contained in it. */
  readonly contained: readonly Call[];
  readonly recording: readonly Call[];
  readonly closing: readonly Call[];
}

function carries(call: Call, field: string): boolean {
  return call.fields.some((candidate) => candidate.name === field);
}

/** The declared key a call is about, or `null` where it names none. */
export function keyOf(call: Call, field: string): string | null {
  const literal = literalOf(call, field);
  return typeof literal === "string" && literal !== "" ? literal : null;
}

/**
 * The lifecycle of one Blueprint, or a refusal of a document no target could
 * render. `parameterName` is the target's own check of a parameter it must be
 * able to bind.
 */
export function readLifecycle(
  blueprint: ResolvedIntegrationBlueprint,
  parameterName: (name: string) => string,
): Lifecycle {
  const calls = blueprint.calls.map(readCall);
  const known: string[] = Object.values(OPERATION_IDS);
  for (const call of calls) {
    if (!known.includes(call.operationId)) {
      refuse(`this target has no call for the operation ${call.operationId}`);
    }
    parameters(call).forEach(parameterName);
  }

  const credentials = calls.flatMap((call) => call.credentials);
  const credential = credentials[0];
  if (credential === undefined) return refuse("no call of the Blueprint carries a credential");
  for (const other of credentials) {
    if (other.binding.environmentVariable !== credential.binding.environmentVariable) {
      refuse("the calls of the Blueprint name different credentials, and a generated file has one");
    }
  }
  if (credential.binding.environmentVariable !== ENVIRONMENT.apiKey) {
    // Every secret a file reads comes with instructions for setting it, and
    // the catalogue holds those for the variables it knows.
    refuse(
      `the catalogue has no setup instructions for the environment variable ` +
        `${credential.binding.environmentVariable}`,
    );
  }

  const starts = calls.filter((call) => call.operationId === OPERATION_IDS.start);
  const tasks = starts.filter((call) => !carries(call, FIELD.parent));
  const start = tasks[0];
  if (start === undefined || tasks.length > 1) {
    return refuse(`a Blueprint has one start of the work itself, and this one has ${tasks.length}`);
  }

  const { calls: _read, ...header } = blueprint;
  return {
    header,
    calls,
    credential,
    start,
    contained: starts.filter((call) => carries(call, FIELD.parent)),
    recording: calls.filter((call) => call.operationId === OPERATION_IDS.record),
    closing: calls.filter((call) => call.operationId === OPERATION_IDS.close),
  };
}
