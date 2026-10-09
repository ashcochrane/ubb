/**
 * A Blueprint read as the lifecycle every target renders: one start of the
 * work, the starts of work contained in it, the records and the closes.
 *
 * Target-neutral. A Blueprint names real v1 operations; which of them a call
 * is, and the few request fields a lifecycle is built around, are the same
 * whatever file is written. What each target DOES with an operation — an SDK
 * method, or a route and a body — is that target's own.
 */
import {
  refuse,
  type DiagnosticCode,
  type ResolvedIntegrationBlueprint,
} from "./blueprint.ts";
import { ENVIRONMENT } from "./catalogue.ts";
import type { components } from "./generated/v1";
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
  measurements: "measurements",
} as const;

/**
 * What a stop is explained by, in the order every target states it: the
 * scope and the reason, in the order a shell file's stop metadata has always
 * carried them, then how the stop was applied and what it was measured on,
 * in the order the acknowledgement publishes them (#569; ADR-0019 §1). Every
 * target states each one by name and works none of them out (#585): a field
 * that does not apply is null, and the two figures are signed. Typed against
 * the contract, so a field it stops publishing stops compiling.
 */
export const STOP_FIELDS = [
  "stop_scope",
  "stop_reason",
  "trigger_source",
  "stop_bound_micros",
  "stop_measured_micros",
] as const satisfies readonly (keyof components["schemas"]["RecordUsageResponse"])[];

export type StopField = (typeof STOP_FIELDS)[number];

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

/**
 * The diagnostic a constant quantity is reported with while this version of
 * the renderer cannot write its declared value (#571). Typed by the contract,
 * so the day the ticket that renders a constant (#584) removes the member,
 * this stops compiling — and goes with it.
 */
const NOT_RENDERABLE: DiagnosticCode = "constant_measurement_not_renderable";

/**
 * Every quantity a Blueprint reports this Code Builder version cannot yet
 * generate the value of (#571), as its diagnostic addresses it:
 * `<event type>:<code>`. The one reading of that diagnostic: the console
 * shows the same tokens, and asks this too.
 */
export function notRenderableAddresses(
  blueprint: Pick<ResolvedIntegrationBlueprint, "diagnostics">,
): ReadonlySet<string> {
  const addressed = new Set<string>();
  for (const diagnostic of blueprint.diagnostics) {
    if (
      diagnostic.code === NOT_RENDERABLE &&
      diagnostic.object_kind === "measurement" &&
      typeof diagnostic.key === "string"
    ) {
      addressed.add(diagnostic.key);
    }
  }
  return addressed;
}

/** Whether the value under `key` of a call's `field` is one of those: a
 * quantity's value, matched on the call's own Event Type and the key exactly
 * as declared — no token name is decoded. */
export function isNotRenderableValue(
  addresses: ReadonlySet<string>,
  eventType: string | null,
  field: string,
  key: string,
): boolean {
  return field === FIELD.measurements && eventType !== null && addresses.has(`${eventType}:${key}`);
}

/**
 * Every such value marked as what it is rather than left looking
 * unconfigured: the tenant declared it, and a file that called it missing
 * would be the false explanation the diagnostic exists to replace. Only a
 * value that already reads as unconfigured is marked: one the Blueprint
 * carries is never taken away.
 */
function withNotRenderable(calls: readonly Call[], blueprint: ResolvedIntegrationBlueprint): Call[] {
  const addresses = notRenderableAddresses(blueprint);
  if (addresses.size === 0) return [...calls];
  return calls.map((call) => {
    const eventType = keyOf(call, FIELD.eventType);
    return {
      ...call,
      fields: call.fields.map((field) =>
        field.shape !== "keyed"
          ? field
          : {
              ...field,
              entries: field.entries.map((entry) =>
                entry.value?.binding.kind === "unconfigured" &&
                isNotRenderableValue(addresses, eventType, field.name, entry.keyText)
                  ? { ...entry, value: { ...entry.value, binding: { kind: "not_renderable" } } }
                  : entry,
              ),
            },
      ),
    };
  });
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
  const calls = withNotRenderable(blueprint.calls.map(readCall), blueprint);
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
