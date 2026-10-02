/**
 * What a shell artifact is made of, decided once for all its files.
 *
 * The runnable file, the call-site blocks, the request previews and the
 * verify script name the same functions, ask for the same parameters and send
 * the same bodies, so those are settled here and each file is written from
 * the result.
 *
 * THE WIRE, WHICH THIS TARGET OWNS. There is no SDK between a shell file and
 * the API, so what the Python target leaves to the SDK is this renderer's
 * knowledge: the route of each operation a Blueprint names (`ROUTES`), which
 * of a call's tokens fills a place in that route and not a key of the body,
 * and the two fields a close may carry beside its outcome. Each is checked
 * against the committed contract where it is written down: a route the
 * contract no longer publishes for that operation, or a field its request no
 * longer has, stops compiling.
 *
 * A token is still placed by its name and its position and never by what its
 * field means (`../tokens.ts`). A one-segment token is a key of the body
 * under exactly that name, unless the route has a place of that name.
 *
 * HOW A RUNTIME VALUE IS PASSED IS DECIDED BY A DECLARED FACT, and by nothing
 * else. A shell argument is always text, so each parameter is one of:
 *
 * - `text`: a JSON string. The default.
 * - `number`: a keyed entry that declares a `value_type`. A whole number,
 *   checked as text and carried exactly or refused.
 * - `file`: a keyed entry that declares a `source_path`, on a call whose
 *   response is declared to be JSON. The path of a file holding the
 *   supplier's response, which the declared path is then read off.
 * - `cost`: a field that declares an `amount_representation`. A supplier's
 *   cost, converted to whole micros on its digits.
 * - `place`: a token named for a place in the route. Written into the URL.
 * - `unread`: a keyed entry that declares a `source_path` this target has no
 *   way to read. Still asked for, so the call's shape is the declared one;
 *   the value is written as a call that raises.
 */
import { refuse, type Json, type ResolvedIntegrationBlueprint } from "../blueprint.ts";
import {
  AMOUNT_REPRESENTATION,
  RESPONSE_REPRESENTATION,
  SHELL_FILE,
} from "../catalogue.ts";
import { tokenStatement } from "../comments.ts";
import type { components, operations, paths } from "../generated/v1";
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
  factOfField,
  literalOf,
  parameters,
  type Call,
  type Fact,
  type Literal,
  type SecretReference,
  type Token,
} from "../tokens.ts";
import { parameterName } from "./syntax.ts";

type OperationId = keyof operations;

/** The paths the contract publishes a POST of this operation at. */
type PathOf<Id extends OperationId> = {
  [Path in keyof paths]: paths[Path] extends { post: operations[Id] } ? Path : never;
}[keyof paths];

export interface Route {
  readonly method: "POST";
  /** As the contract spells it, with `{name}` where a value goes. */
  readonly path: string;
}

function post<Id extends OperationId>(_operationId: Id, path: PathOf<Id>): Route {
  return { method: "POST", path };
}

/** The route of each operation this target has a call for. */
const ROUTES: Readonly<Record<string, Route>> = {
  [OPERATION_IDS.start]: post(OPERATION_IDS.start, "/api/v1/tasks"),
  [OPERATION_IDS.record]: post(OPERATION_IDS.record, "/api/v1/metering/usage"),
  [OPERATION_IDS.close]: post(OPERATION_IDS.close, "/api/v1/tasks/{task_id}/close"),
};

/**
 * The fields a close may carry beside the ones a Blueprint names. Not asked
 * for unless given: why work failed is said only where it did.
 */
const CLOSE_MAY_CARRY: readonly (keyof components["schemas"]["CloseTaskRequest"])[] = [
  SHELL_FILE.outcomeReason,
  SHELL_FILE.reasonDetail,
];

/** The field of a close that says how the work ended. */
const OUTCOME: keyof components["schemas"]["CloseTaskRequest"] = "outcome";

/** The field a stop is reported with: the key its event was sent under. */
const IDEMPOTENCY_KEY: keyof components["schemas"]["RecordUsageRequest"] = "idempotency_key";

export type Use = "text" | "number" | "file" | "cost" | "place" | "unread";

export interface Parameter {
  /** Exactly as the Blueprint names it. */
  readonly name: string;
  readonly use: Use;
  /** `false` for a field a call may carry and need not. */
  readonly required: boolean;
}

/** What is written where a value goes. */
export type Value =
  | { readonly kind: "literal"; readonly value: Json }
  | { readonly kind: "parameter"; readonly parameter: Parameter }
  | {
      readonly kind: "read";
      readonly parameter: Parameter;
      readonly path: readonly string[];
      /** The provenance of the declared path itself. */
      readonly declared: string;
    }
  | { readonly kind: "unconfigured"; readonly token: string }
  | {
      readonly kind: "cost";
      readonly parameter: Parameter;
      readonly representation: string;
      /** The currency the call declares the cost in, or none. */
      readonly declared: string;
    };

/** One declared key of a keyed field, and the value under it. */
export interface Member {
  readonly key: string;
  /** The provenance of the key and of every fact declared of it. */
  readonly comments: readonly string[];
  /** `null` where the document carries no value: stated, and not sent. */
  readonly value: Value | null;
}

/** One key of a request's body: one value, or an object of declared keys. */
export type BodyField =
  | {
      readonly shape: "scalar";
      readonly name: string;
      readonly comments: readonly string[];
      readonly value: Value;
      /** Sent only where its parameter was given. */
      readonly optional: boolean;
    }
  | {
      readonly shape: "keyed";
      readonly name: string;
      readonly members: readonly Member[];
    };

/**
 * The parameters the boundary declares a failure through: the ones the close
 * takes for the work, its outcome, and why. By the names the Blueprint gives
 * them, which are not assumed to be the names of the fields they fill.
 */
export interface Closing {
  readonly work: Parameter;
  readonly outcome: Parameter;
  readonly outcomeReason: Parameter;
  readonly reasonDetail: Parameter;
}

export type CallKind = "start" | "subtask" | "record" | "close";

export interface CallPlan {
  readonly kind: CallKind;
  readonly call: Call;
  /** The function a call site calls. */
  readonly name: string;
  readonly route: Route;
  /** Every parameter the function takes, required ones first. */
  readonly parameters: readonly Parameter[];
  readonly body: readonly BodyField[];
  /** The parameter that fills each place in the route, by the place's name. */
  readonly places: Readonly<Record<string, Parameter>>;
  /** The parameter a stop's event was sent under. Records only. */
  readonly sentUnder: Parameter | null;
  /** The parameter that names the work this is contained in. Subtasks only. */
  readonly parent: Parameter | null;
  /** Closes only. */
  readonly closing: Closing | null;
}

export interface Plan {
  readonly header: Header;
  readonly calls: readonly Call[];
  readonly credential: Token<SecretReference>;
  readonly start: CallPlan;
  readonly subtasks: readonly CallPlan[];
  readonly records: readonly CallPlan[];
  readonly close: CallPlan;
}

function isALiteral(token: Token): token is Token<Literal> {
  return token.binding.kind === "literal";
}

function provenance(tokens: readonly Token[]): string[] {
  return tokens.filter(isALiteral).map(tokenStatement);
}

function factTokens(facts: readonly Fact[]): Token[] {
  return facts.map((fact) => fact.token);
}

function segments(path: Json): readonly string[] {
  if (!Array.isArray(path) || path.some((segment) => typeof segment !== "string")) {
    return refuse("a declared source path is not a list of segments");
  }
  return path as readonly string[];
}

const PLACE = /\{([^{}]+)\}/g;

/** The names of the places in a route. */
function places(route: Route): string[] {
  return [...route.path.matchAll(PLACE)].map((match) => match[1]!);
}

/** A route with each of its places written as `written` says. */
export function routeWith(call: CallPlan, written: (parameter: Parameter) => string): string {
  return call.route.path.replace(PLACE, (_place, name: string) => written(call.places[name]!));
}

/** The parameter a field of the body is filled from, where it is one. */
function parameterOf(body: readonly BodyField[], name: string): Parameter | undefined {
  const field = body.find((candidate) => candidate.name === name);
  return field?.shape === "scalar" && field.value.kind === "parameter"
    ? field.value.parameter
    : undefined;
}

/** One call, with every parameter given its use and every key its value. */
function planCall(kind: CallKind, call: Call, name: string): CallPlan {
  const route = ROUTES[call.operationId];
  if (route === undefined) {
    return refuse(`this target has no route for the operation ${call.operationId}`);
  }
  const inTheRoute = places(route);
  const uses = new Map<string, Use>();
  const used = (parameter: string, use: Use): Parameter => {
    const already = uses.get(parameter);
    if (already !== undefined && already !== use) {
      refuse(
        `the parameter ${parameter} of ${call.operationId} is asked for as two ` +
          `kinds of value: ${already} and ${use}`,
      );
    }
    uses.set(parameter, use);
    return { name: parameter, use, required: true };
  };

  const readable =
    factOfField(call, FIELD.eventType, FACT.responseRepresentation) ===
    RESPONSE_REPRESENTATION.json;
  const body: BodyField[] = [];
  const filled: Record<string, Parameter> = {};

  for (const field of call.fields) {
    if (field.shape === "keyed") {
      const members: Member[] = field.entries.map((entry) => {
        const comments = provenance([entry.key, ...factTokens(entry.facts)]);
        const bound = entry.value;
        if (bound === null) return { key: entry.keyText, comments, value: null };
        if (bound.binding.kind === "literal") {
          return {
            key: entry.keyText,
            comments,
            value: { kind: "literal", value: bound.binding.value },
          };
        }
        if (bound.binding.kind === "unconfigured") {
          return { key: entry.keyText, comments, value: { kind: "unconfigured", token: bound.name } };
        }
        const stated = entry.facts.find((fact) => fact.element === FACT.sourcePath);
        if (stated !== undefined) {
          const declared = segments(stated.token.binding.value);
          // A path is read off JSON and off nothing else. Where the response
          // is declared to be something this target cannot hold, the value
          // keeps its place and is written as a call that raises.
          const parameter = used(bound.binding.name, readable ? "file" : "unread");
          return {
            key: entry.keyText,
            comments,
            value: readable
              ? {
                  kind: "read",
                  parameter,
                  path: declared,
                  declared: tokenStatement(stated.token),
                }
              : { kind: "unconfigured", token: bound.name },
          };
        }
        const use: Use = factNamed(entry.facts, FACT.valueType) === undefined ? "text" : "number";
        return {
          key: entry.keyText,
          comments,
          value: { kind: "parameter", parameter: used(bound.binding.name, use) },
        };
      });
      body.push({ shape: "keyed", name: field.name, members });
      continue;
    }

    const comments = provenance([field.token, ...factTokens(field.facts)]);
    const binding = field.token.binding;
    if (binding.kind === "parameter" && inTheRoute.includes(field.name)) {
      filled[field.name] = used(binding.name, "place");
      continue;
    }
    if (binding.kind === "literal") {
      body.push({
        shape: "scalar",
        name: field.name,
        comments,
        value: { kind: "literal", value: binding.value },
        optional: false,
      });
      continue;
    }
    if (binding.kind === "unconfigured") {
      body.push({
        shape: "scalar",
        name: field.name,
        comments,
        value: { kind: "unconfigured", token: field.name },
        optional: false,
      });
      continue;
    }
    const representation = factNamed(field.facts, FACT.amountRepresentation);
    if (representation !== undefined) {
      if (
        typeof representation !== "string" ||
        !(Object.values(AMOUNT_REPRESENTATION) as string[]).includes(representation)
      ) {
        refuse(`${String(representation)} is not an amount representation this target converts`);
      }
      const declared = literalOf(call, FIELD.currency);
      body.push({
        shape: "scalar",
        name: field.name,
        comments,
        value: {
          kind: "cost",
          parameter: used(binding.name, "cost"),
          representation: representation as string,
          declared: typeof declared === "string" ? declared : "",
        },
        optional: false,
      });
      continue;
    }
    body.push({
      shape: "scalar",
      name: field.name,
      comments,
      value: { kind: "parameter", parameter: used(binding.name, "text") },
      optional: false,
    });
  }

  for (const place of inTheRoute) {
    if (filled[place] === undefined) {
      refuse(`the route of ${call.operationId} has a place for ${place}, and no token fills it`);
    }
  }

  // Required parameters in the order the document first names them.
  const asked: Parameter[] = parameters(call).map((parameter) => ({
    name: parameter,
    use: uses.get(parameter)!,
    required: true,
  }));

  let closing: Closing | null = null;
  if (kind === "close") {
    for (const fieldName of CLOSE_MAY_CARRY) {
      if (call.fields.some((field) => field.name === fieldName)) continue;
      if (asked.some((parameter) => parameter.name === fieldName)) {
        refuse(`the close asks for ${fieldName} as the value of another field`);
      }
      const parameter: Parameter = { name: fieldName, use: "text", required: false };
      asked.push(parameter);
      body.push({
        shape: "scalar",
        name: fieldName,
        comments: [],
        value: { kind: "parameter", parameter },
        optional: true,
      });
    }
    // The boundary declares a failure through this call, so each thing it
    // says must be the caller's to say: a parameter, under whatever name the
    // document gave it.
    const said = (fieldName: string): Parameter =>
      parameterOf(body, fieldName) ??
      refuse(`the close takes no parameter for ${fieldName}, and a failure is declared through it`);
    const work = Object.values(filled)[0];
    if (work === undefined) return refuse("a close names no work in its route");
    closing = {
      work,
      outcome: said(OUTCOME),
      outcomeReason: said(SHELL_FILE.outcomeReason),
      reasonDetail: said(SHELL_FILE.reasonDetail),
    };
  }

  let sentUnder: Parameter | null = null;
  if (kind === "record") {
    sentUnder =
      parameterOf(body, IDEMPOTENCY_KEY) ??
      refuse(
        `the record ${name} names no ${IDEMPOTENCY_KEY} parameter, and a stop is ` +
          `reported with the key its event was sent under`,
      );
  }

  return {
    kind,
    call,
    name,
    route,
    parameters: asked,
    body,
    places: filled,
    sentUnder,
    parent: kind === "subtask" ? (parameterOf(body, FIELD.parent) ?? null) : null,
    closing,
  };
}

/** The plan for one Blueprint, or a refusal of a document it cannot render. */
export function plan(blueprint: ResolvedIntegrationBlueprint): Plan {
  const { header, calls, credential, start, contained, recording, closing } = readLifecycle(
    blueprint,
    parameterName,
  );
  const close = closing[0];
  if (close === undefined || closing.length > 1) {
    return refuse(`a Blueprint has one close of the work, and this one has ${closing.length}`);
  }

  const fixed = [SHELL_FILE.startTask, SHELL_FILE.unitOfWork, SHELL_FILE.closeTask];
  const wanted: Wanted[] = [
    ...contained.map((call) => ({
      prefixes: [SHELL_FILE.startSubtaskPrefix],
      key: keyOf(call, FIELD.kindOfWork),
    })),
    ...recording.map((call) => ({
      prefixes: [SHELL_FILE.recordPrefix],
      key: keyOf(call, FIELD.eventType),
    })),
  ];
  const named = nameTails(wanted, fixed, SHELL_FILE.unkeyed);

  return {
    header,
    calls,
    credential,
    start: planCall("start", start, SHELL_FILE.startTask),
    subtasks: contained.map((call, index) =>
      planCall("subtask", call, `${SHELL_FILE.startSubtaskPrefix}_${named[index]!}`),
    ),
    records: recording.map((call, index) =>
      planCall(
        "record",
        call,
        `${SHELL_FILE.recordPrefix}_${named[contained.length + index]!}`,
      ),
    ),
    close: planCall("close", close, SHELL_FILE.closeTask),
  };
}
