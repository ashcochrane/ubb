/**
 * What a Python artifact is made of, decided once for all its files.
 *
 * The module, the call-site blocks and the verify script name the same
 * functions and ask for the same parameters, so those are settled here and
 * each file is written from the result.
 *
 * THE SDK'S SURFACE, WHICH THIS TARGET OWNS. A Blueprint names real v1
 * operations; which SDK method reaches each is this renderer's knowledge
 * (#184 §1) and is written down in `OPERATIONS`. A field of a request is
 * passed to that method under the field's own name, never another. The close
 * needs no generated function: the handle a start returns declares the
 * outcome.
 *
 * NAMES. A generated function is named for the declared key it is about, by
 * `nameTail`. That is this renderer's naming and never a second spelling of
 * the key, which is only ever written as a literal. Two keys that would share
 * a name BOTH take a suffix that is a function of the key — so adding an
 * Event Type can make an existing function's name disappear, which a call
 * site notices, and can never hand that name to another Event Type, which it
 * would not.
 */
import { refuse, type ResolvedIntegrationBlueprint } from "../blueprint.ts";
import { ENVIRONMENT, PYTHON } from "../catalogue.ts";
import {
  literalOf,
  parameters,
  readCall,
  type Call,
  type SecretReference,
  type Token,
} from "../tokens.ts";
import { nameTail, parameterName, shortHash, unshadowed } from "./syntax.ts";

/** The operations this target has a call for, and the SDK method of each. */
export const OPERATIONS = {
  start: { operationId: "api_v1_task_endpoints_start_task", method: "start_task" },
  record: { operationId: "api_v1_metering_endpoints_record_usage", method: "record_usage" },
  close: { operationId: "api_v1_task_endpoints_close_task", method: null },
} as const;

/**
 * The request fields this target knows by name, because the SDK's surface is
 * built around them: the one that says work is contained in other work, the
 * two whose literal a generated function is named for, and the one a cost is
 * denominated in.
 */
export const FIELD = {
  parent: "parent_task_id",
  kindOfWork: "task_type",
  eventType: "event_type",
  currency: "currency",
} as const;

/** The declared facts this target acts on, by the last segment of their name. */
export const FACT = {
  sourcePath: "source_path",
  responseRepresentation: "response_shape_representation",
  amountRepresentation: "amount_representation",
  pricingMode: "pricing_mode",
} as const;

/** The document without its calls: what a file's header states. */
export type Header = Omit<ResolvedIntegrationBlueprint, "calls">;

export interface StartPlan {
  readonly call: Call;
  readonly parameters: readonly string[];
  /** The function a call site calls. */
  readonly name: string;
}

export interface RecordPlan {
  readonly call: Call;
  readonly parameters: readonly string[];
  readonly name: string;
  readonly backfillName: string;
  /** The parameter the backfill path adds, spelled so it collides with none. */
  readonly recordedAt: string;
}

/** The names the module uses for things of its own. */
export interface Internal {
  readonly client: string;
  readonly clientHolder: string;
  readonly logger: string;
  readonly notReady: string;
  readonly notConfigured: string;
  readonly toMicros: string;
  readonly pinCurrency: string;
  readonly minorUnit: string;
  readonly attribute: string;
  readonly startTask: string;
  readonly send: (record: RecordPlan) => string;
}

export interface Plan {
  /** Everything of the document but its calls, which are read into `calls`:
   * no writer is handed a raw token. */
  readonly header: Header;
  readonly calls: readonly Call[];
  readonly credential: Token<SecretReference>;
  readonly start: StartPlan;
  readonly subtasks: readonly StartPlan[];
  readonly records: readonly RecordPlan[];
  readonly internal: Internal;
}

function keyOf(call: Call, field: string): string | null {
  const literal = literalOf(call, field);
  return typeof literal === "string" && literal !== "" ? literal : null;
}

interface Wanted {
  readonly prefixes: readonly string[];
  readonly key: string | null;
}

/**
 * The tail of each wanted function's name — the part after its prefix — so
 * that no two functions share a name.
 */
function nameTails(wanted: readonly Wanted[], fixed: readonly string[]): string[] {
  const plain = wanted.map((entry) => (entry.key === null ? null : nameTail(entry.key)));
  const names = (index: number, tail: string) =>
    wanted[index]!.prefixes.map((prefix) => `${prefix}_${tail}`);

  const count = new Map<string, number>();
  for (const name of fixed) count.set(name, 1);
  plain.forEach((tail, index) => {
    if (tail === null) return;
    for (const name of names(index, tail)) count.set(name, (count.get(name) ?? 0) + 1);
  });

  const taken = new Set<string>(fixed);
  const settled = plain.map((tail, index) => {
    if (tail === null) return null;
    const shared = names(index, tail).some((name) => (count.get(name) ?? 0) > 1);
    const own = shared ? `${tail}_${shortHash(wanted[index]!.key!)}` : tail;
    names(index, own).forEach((name) => taken.add(name));
    return own;
  });

  // A call with no declared key to be named for is named for its place. It
  // cannot run — it has no key because nothing is selected or declared — so
  // its name is not one a working call site depends on.
  return settled.map((tail, index) => {
    if (tail !== null) return tail;
    let own: string = PYTHON.unkeyed;
    for (let suffix = 2; names(index, own).some((name) => taken.has(name)); suffix += 1) {
      own = `${PYTHON.unkeyed}_${suffix}`;
    }
    names(index, own).forEach((name) => taken.add(name));
    return own;
  });
}

function carries(call: Call, field: string): boolean {
  return call.fields.some((candidate) => candidate.name === field);
}

/** The plan for one Blueprint, or a refusal of a document it cannot render. */
export function plan(blueprint: ResolvedIntegrationBlueprint): Plan {
  if (blueprint.sdk_major_version !== PYTHON.sdkMajorVersion) {
    refuse(
      `this target is written against SDK major ${PYTHON.sdkMajorVersion}, and the ` +
        `Blueprint names ${String(blueprint.sdk_major_version)}`,
    );
  }

  const calls = blueprint.calls.map(readCall);
  const known: string[] = Object.values(OPERATIONS).map((operation) => operation.operationId);
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
      refuse("the calls of the Blueprint name different credentials, and a module has one client");
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

  const starts = calls.filter((call) => call.operationId === OPERATIONS.start.operationId);
  const tasks = starts.filter((call) => !carries(call, FIELD.parent));
  const contained = starts.filter((call) => carries(call, FIELD.parent));
  const recording = calls.filter((call) => call.operationId === OPERATIONS.record.operationId);
  const start = tasks[0];
  if (start === undefined || tasks.length > 1) {
    return refuse(`a Blueprint has one start of the work itself, and this one has ${tasks.length}`);
  }

  const fixed = [PYTHON.startTask, PYTHON.unitOfWork];
  const wanted: Wanted[] = [
    ...contained.map((call) => ({
      prefixes: [PYTHON.startSubtaskPrefix],
      key: keyOf(call, FIELD.kindOfWork),
    })),
    ...recording.map((call) => ({
      prefixes: [PYTHON.recordPrefix, PYTHON.backfillPrefix],
      key: keyOf(call, FIELD.eventType),
    })),
  ];
  const named = nameTails(wanted, fixed);

  const subtasks: StartPlan[] = contained.map((call, index) => ({
    call,
    parameters: parameters(call),
    name: `${PYTHON.startSubtaskPrefix}_${named[index]!}`,
  }));
  const records: RecordPlan[] = recording.map((call, index) => {
    const asked = parameters(call);
    const tail = named[contained.length + index]!;
    return {
      call,
      parameters: asked,
      name: `${PYTHON.recordPrefix}_${tail}`,
      backfillName: `${PYTHON.backfillPrefix}_${tail}`,
      recordedAt: unshadowed(PYTHON.recordedAt, new Set(asked)),
    };
  });

  // The module's own names are spelled so that no parameter of any call is
  // spelled like one: a declared name can never stand in front of them.
  const taken = new Set<string>([
    ...calls.flatMap(parameters),
    ...records.map((record) => record.recordedAt),
    ...fixed,
    ...subtasks.map((subtask) => subtask.name),
    ...records.flatMap((record) => [record.name, record.backfillName]),
  ]);
  const ownName = (wantedName: string) => {
    const name = unshadowed(wantedName, taken);
    taken.add(name);
    return name;
  };
  const sends = new Map(
    records.map((record) => [
      record,
      ownName(`_send_${record.name.slice(PYTHON.recordPrefix.length + 1)}`),
    ]),
  );
  const internal: Internal = {
    client: ownName("_client"),
    clientHolder: ownName("_CLIENT"),
    logger: ownName("_LOGGER"),
    notReady: ownName("_not_ready"),
    notConfigured: ownName("_not_configured"),
    toMicros: ownName("_to_micros"),
    pinCurrency: ownName("_pin_currency"),
    minorUnit: ownName("_minor_unit"),
    attribute: ownName("_attribute"),
    startTask: ownName("_start_task"),
    send: (record) => sends.get(record)!,
  };

  const { calls: _read, ...header } = blueprint;
  return {
    header,
    calls,
    credential,
    start: { call: start, parameters: parameters(start), name: PYTHON.startTask },
    subtasks,
    records,
    internal,
  };
}
