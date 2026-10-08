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
 * the rule every target shares (`../names.ts`).
 */
import { refuse, type ResolvedIntegrationBlueprint } from "../blueprint.ts";
import { PYTHON } from "../catalogue.ts";
import {
  FACT,
  FIELD,
  keyOf,
  OPERATION_IDS,
  readLifecycle,
  type Header,
} from "../lifecycle.ts";
import { nameTails, type Wanted } from "../names.ts";
import {
  factNamed,
  parameters,
  type Call,
  type Fact,
  type SecretReference,
  type Token,
} from "../tokens.ts";
import { parameterName, unshadowed } from "./syntax.ts";

export { FACT, FIELD, type Header } from "../lifecycle.ts";

/** The operations this target has a call for, and the SDK method of each. */
export const OPERATIONS = {
  start: { operationId: OPERATION_IDS.start, method: "start_task" },
  record: { operationId: OPERATION_IDS.record, method: "record_usage" },
  close: { operationId: OPERATION_IDS.close, method: null },
} as const;

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
  readonly notRenderable: string;
  readonly toMicros: string;
  readonly pinCurrency: string;
  readonly minorUnit: string;
  readonly readAmount: string;
  readonly readCurrency: string;
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

/**
 * Refuses a call that asks for one parameter both as something a declared
 * path is read off and as a value sent as it is. The response object is the
 * one parameter read by a path, and a document that also sent it whole —
 * under `currency`, say — would have the module post the supplier's response
 * as a field's value without a word.
 */
function oneUseEach(call: Call): void {
  const read = new Set<string>();
  const sent = new Set<string>();
  const sort = (token: Token | null, facts: readonly Fact[]) => {
    if (token?.binding.kind !== "parameter") return;
    const into = factNamed(facts, FACT.sourcePath) === undefined ? sent : read;
    into.add(token.binding.name);
  };
  for (const field of call.fields) {
    if (field.shape === "scalar") sort(field.token, field.facts);
    else field.entries.forEach((entry) => sort(entry.value, entry.facts));
  }
  for (const parameter of read) {
    if (sent.has(parameter)) {
      refuse(
        `the parameter ${parameter} of ${call.operationId} is asked for as a ` +
          `response a path is read off and as a value sent as it is`,
      );
    }
  }
}

/** The plan for one Blueprint, or a refusal of a document it cannot render. */
export function plan(blueprint: ResolvedIntegrationBlueprint): Plan {
  if (blueprint.sdk_major_version !== PYTHON.sdkMajorVersion) {
    refuse(
      `this target is written against SDK major ${PYTHON.sdkMajorVersion}, and the ` +
        `Blueprint names ${String(blueprint.sdk_major_version)}`,
    );
  }

  const { header, calls, credential, start, contained, recording } = readLifecycle(
    blueprint,
    parameterName,
  );
  calls.forEach(oneUseEach);

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
  const named = nameTails(wanted, fixed, PYTHON.unkeyed);

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
    notRenderable: ownName("_not_renderable"),
    toMicros: ownName("_to_micros"),
    pinCurrency: ownName("_pin_currency"),
    minorUnit: ownName("_minor_unit"),
    readAmount: ownName("_read_amount"),
    readCurrency: ownName("_read_currency"),
    attribute: ownName("_attribute"),
    startTask: ownName("_start_task"),
    send: (record) => sends.get(record)!,
  };

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
