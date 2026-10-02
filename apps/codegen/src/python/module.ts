/**
 * The module: the one file a tenant drops in and never edits.
 *
 * Everything the Blueprint resolved is in here and nowhere else — every
 * literal, every declared path, every fact stated beside the value it is
 * about — so that when configuration changes, replacing this file is the
 * whole of regenerating.
 *
 * THE THREE CLASSES ARE SHAPES. A `platform_known` token is written as a
 * literal. A `runtime_bound` token is a required keyword parameter of the
 * function for its call, named exactly as the Blueprint names it. A
 * `secret_reference` is `os.environ[...]`. A literal with no configured value
 * keeps its place and is written as a call that raises.
 *
 * A CALL THAT IS NOT READY RAISES FIRST. Its function opens with a guard
 * naming the operation, its verdict and every token with no configured
 * value, so nothing is sent by a call the Blueprint says cannot run — and the
 * call itself is still written beneath it, which is what shows the shape.
 *
 * THE DECLARED FACTS THIS TARGET ACTS ON, by the last segment of their name.
 * Every other fact is stated in a comment and changes nothing:
 *
 * - `source_path` under a keyed entry: the entry's value is read off the
 *   parameter by that path, and
 *   `response_shape_representation` on the call's Event Type says how — by
 *   subscript for JSON, by attribute for a Python object. A segment is only
 *   ever written as itself; one Python cannot spell as an attribute is
 *   reached with `getattr`, which changes the syntax and not the name. With
 *   no representation there is no way to read the path, and the value is
 *   written as a call that raises.
 * - `amount_representation` on a field: the parameter is a supplier's cost,
 *   converted to whole micros once, in the currency the call's `currency`
 *   field declares.
 * - `pricing_mode` on the kind of work: which sentence says what delivering
 *   the work does.
 */
import { BlueprintNotRenderable, type Json } from "../blueprint.ts";
import {
  AMOUNT_REPRESENTATIONS,
  BASE_URL_DEFAULT,
  COMMENTS,
  ENVIRONMENT,
  MESSAGES,
  MICROS_PER_MINOR_UNIT,
  PRICING_MODE_COMMENTS,
  PYTHON,
  READINESS_COMMENTS,
  REMEDIATION,
} from "../catalogue.ts";
import { hash, publication, statement, tokenStatement } from "../comments.ts";
import {
  factOfField,
  literalOf,
  unconfigured,
  type Call,
  type Entry,
  type Field,
  type KeyedField,
  type Literal,
  type Parameter,
  type ScalarField,
  type Token,
  type Unconfigured,
} from "../tokens.ts";
import { OPERATIONS, type Plan, type RecordPlan, type StartPlan } from "./plan.ts";
import { fresh, isIdentifier, pyLiteral, pyString } from "./syntax.ts";

const INDENT = "    ";

/** What the module turned out to need, found while writing its calls. */
interface Uses {
  notReady: boolean;
  reportedCost: boolean;
  attribute: boolean;
}

function refuse(message: string): never {
  throw new BlueprintNotRenderable(message);
}

// ---------------------------------------------------------------------------
// The header
// ---------------------------------------------------------------------------

function header(plan: Plan): string[] {
  const { blueprint } = plan;
  const fingerprint = blueprint.configuration_fingerprint ?? null;
  const lines: string[] = [
    ...COMMENTS.generated,
    "",
    statement("schema_version", blueprint.schema_version),
    statement("renderer_contract_version", blueprint.renderer_contract_version),
    statement("sdk_major_version", blueprint.sdk_major_version ?? null),
    statement("target", blueprint.target),
    statement("configuration_fingerprint", fingerprint),
    ...(fingerprint === null ? COMMENTS.draftPreview : COMMENTS.fingerprint),
    "",
    statement("readiness", blueprint.readiness),
    ...READINESS_COMMENTS[blueprint.readiness],
    "",
  ];

  if (blueprint.diagnostics.length === 0) {
    lines.push(...COMMENTS.noDiagnostics);
  } else {
    lines.push(...COMMENTS.diagnostics);
    for (const diagnostic of blueprint.diagnostics) {
      const remediation = REMEDIATION[diagnostic.code];
      if (remediation === undefined) {
        refuse(`the catalogue has no remediation for the diagnostic ${diagnostic.code}`);
      }
      lines.push(
        "",
        statement("diagnostic", diagnostic.code, [
          ["severity", diagnostic.severity],
          [diagnostic.object_kind, diagnostic.key ?? null],
          ["field", diagnostic.field ?? null],
        ]),
        ...remediation,
      );
      if (diagnostic.remediation_request != null) {
        lines.push(
          ...COMMENTS.remediationRequest,
          statement("remediation_request", diagnostic.remediation_request as unknown as Json),
        );
      }
    }
  }

  // Every declaration anything in this file was read from, each once, with
  // the publication it was read from where there was one.
  const declarations: string[] = [];
  for (const call of plan.calls) {
    for (const token of everyToken(call)) {
      if (token.provenance === null) continue;
      const line = statement(
        token.provenance.object_kind,
        token.provenance.key,
        publication(token.provenance),
      );
      if (!declarations.includes(line)) declarations.push(line);
    }
  }
  if (declarations.length > 0) {
    lines.push("", ...COMMENTS.resolvedFrom, ...declarations);
  }

  lines.push("", ...COMMENTS.legend);
  return lines.map((line) => (line === "" ? "" : `# ${line}`));
}

function everyToken(call: Call): Token[] {
  const tokens: Token[] = [...call.credentials];
  for (const field of call.fields) {
    if (field.shape === "scalar") {
      tokens.push(field.token, ...field.facts.map((fact) => fact.token));
      continue;
    }
    for (const entry of field.entries) {
      tokens.push(entry.key, ...entry.facts.map((fact) => fact.token));
      if (entry.value !== null) tokens.push(entry.value);
    }
  }
  return tokens;
}

// ---------------------------------------------------------------------------
// Values
// ---------------------------------------------------------------------------

type Valued = Token<Literal | Unconfigured | Parameter>;

function notConfigured(plan: Plan, uses: Uses, name: string): string {
  uses.notReady = true;
  return `${plan.internal.notConfigured}(${pyString(name)})`;
}

function plain(plan: Plan, uses: Uses, token: Valued): string {
  switch (token.binding.kind) {
    case "literal":
      return pyLiteral(token.binding.value);
    case "parameter":
      return token.binding.name;
    case "unconfigured":
      return notConfigured(plan, uses, token.name);
  }
}

function fact(facts: readonly { element: string; token: Token<Literal> }[], element: string) {
  return facts.find((candidate) => candidate.element === element)?.token.binding.value;
}

/** A value read off `root` by a declared path, or `null` where this target
 * has no way to read one of that representation. */
function traversal(
  plan: Plan,
  uses: Uses,
  root: string,
  path: Json,
  representation: Json | undefined,
): string | null {
  if (!Array.isArray(path) || path.some((segment) => typeof segment !== "string")) {
    return refuse("a declared source path is not a list of segments");
  }
  const segments = path as readonly string[];
  if (representation === "json") {
    return root + segments.map((segment) => `[${pyString(segment)}]`).join("");
  }
  if (representation === "python_object") {
    return segments.reduce((expression, segment) => {
      if (isIdentifier(segment)) return `${expression}.${segment}`;
      uses.attribute = true;
      return `${plan.internal.attribute}(${expression}, ${pyString(segment)})`;
    }, root);
  }
  return null;
}

function entryValue(plan: Plan, uses: Uses, call: Call, entry: Entry): string | null {
  if (entry.value === null) return null;
  const path = fact(entry.facts, "source_path");
  if (path !== undefined && entry.value.binding.kind === "parameter") {
    const read = traversal(
      plan,
      uses,
      entry.value.binding.name,
      path,
      factOfField(call, "event_type", "response_shape_representation"),
    );
    return read ?? notConfigured(plan, uses, entry.value.name);
  }
  return plain(plan, uses, entry.value);
}

function scalarValue(plan: Plan, uses: Uses, call: Call, field: ScalarField): string {
  const representation = fact(field.facts, "amount_representation");
  if (representation !== undefined && field.token.binding.kind === "parameter") {
    if (!(AMOUNT_REPRESENTATIONS as readonly Json[]).includes(representation)) {
      refuse(`${String(representation)} is not an amount representation this target converts`);
    }
    uses.reportedCost = true;
    const declared = literalOf(call, "currency");
    return (
      `${plan.internal.toMicros}(${field.token.binding.name}, ` +
      `${pyLiteral(representation)}, ` +
      `${plan.internal.pinCurrency}(${pyLiteral(typeof declared === "string" ? declared : "")}, None))`
    );
  }
  return plain(plan, uses, field.token);
}

// ---------------------------------------------------------------------------
// A call to the SDK
// ---------------------------------------------------------------------------

function stated(tokens: readonly Token[], indent: string): string[] {
  return hash(
    tokens
      .filter((token): token is Token<Literal> => token.binding.kind === "literal")
      .map(tokenStatement),
    indent,
  );
}

function argumentLines(plan: Plan, uses: Uses, call: Call, field: Field): string[] {
  const indent = INDENT.repeat(2);
  if (field.shape === "scalar") {
    return [
      ...stated([field.token, ...field.facts.map((declared) => declared.token)], indent),
      `${indent}${field.name}=${scalarValue(plan, uses, call, field)},`,
    ];
  }
  return [`${indent}${field.name}={`, ...entryLines(plan, uses, call, field), `${indent}},`];
}

function entryLines(plan: Plan, uses: Uses, call: Call, field: KeyedField): string[] {
  const indent = INDENT.repeat(3);
  return field.entries.flatMap((entry) => {
    const value = entryValue(plan, uses, call, entry);
    return [
      ...stated([entry.key, ...entry.facts.map((declared) => declared.token)], indent),
      // A key no token gives a value to is stated and not sent.
      ...(value === null ? [] : [`${indent}${pyString(entry.keyText)}: ${value},`]),
    ];
  });
}

function guard(plan: Plan, uses: Uses, call: Call): string[] {
  if (call.readiness === "complete") return [];
  uses.notReady = true;
  const missing = unconfigured(call).map((name) => `, ${pyString(name)}`).join("");
  return [
    ...hash(COMMENTS.notReadyCall, INDENT),
    `${INDENT}${plan.internal.notReady}(${pyString(call.operationId)}, ` +
      `${pyString(call.readiness)}${missing})`,
  ];
}

function signature(name: string, parameters: readonly string[], returns: string): string[] {
  if (parameters.length === 0) return [`def ${name}() -> ${returns}:`];
  return [
    `def ${name}(`,
    `${INDENT}*,`,
    ...parameters.map((parameter) => `${INDENT}${parameter},`),
    `) -> ${returns}:`,
  ];
}

function sdkCall(
  plan: Plan,
  uses: Uses,
  call: Call,
  method: string,
  extra: readonly string[] = [],
): string[] {
  return [
    `${INDENT}return ${plan.internal.client}().${method}(`,
    ...call.fields.flatMap((field) => argumentLines(plan, uses, call, field)),
    ...extra.map((line) => `${INDENT.repeat(2)}${line}`),
    `${INDENT})`,
  ];
}

function passing(parameters: readonly string[]): string[] {
  return parameters.map((parameter) => `${parameter}=${parameter},`);
}

function startFunction(plan: Plan, uses: Uses, start: StartPlan, comments: readonly string[]) {
  return [
    ...hash(comments),
    ...signature(start.name, start.parameters, "StartedTask"),
    ...guard(plan, uses, start.call),
    ...sdkCall(plan, uses, start.call, OPERATIONS.start.method),
  ];
}

function unitOfWork(plan: Plan): string[] {
  const { start } = plan;
  const reserved = ["UBBStopRequested", "contextmanager"];
  const clash = start.parameters.find((parameter) => reserved.includes(parameter));
  if (clash !== undefined) {
    refuse(`the parameter ${clash} is a name the boundary itself must be able to say`);
  }
  const taken = new Set(start.parameters);
  const task = fresh("task", taken);
  const stop = fresh("stop", taken);
  const inner = INDENT.repeat(3);
  return [
    ...hash(COMMENTS.unitOfWork),
    "@contextmanager",
    ...signature(PYTHON.unitOfWork, start.parameters, "Iterator[StartedTask]"),
    `${INDENT}try:`,
    `${INDENT.repeat(2)}with ${plan.internal.startTask}(`,
    ...passing(start.parameters).map((line) => `${inner}${line}`),
    `${INDENT.repeat(2)}) as ${task}:`,
    `${inner}yield ${task}`,
    `${INDENT}except UBBStopRequested as ${stop}:`,
    // The acknowledgement as it stands, by its own description of itself:
    // whatever it carries is logged, and nothing is worked out from it.
    `${INDENT.repeat(2)}${plan.internal.logger}.warning(`,
    `${inner}${pyString(MESSAGES.stop)},`,
    `${inner}${stop}.result,`,
    `${INDENT.repeat(2)})`,
    `${INDENT.repeat(2)}raise`,
  ];
}

function recordFunctions(plan: Plan, uses: Uses, record: RecordPlan): string[] {
  const send = plan.internal.send(record);
  const behaviour = fresh("stop_behavior", new Set([...record.parameters, record.recordedAt]));
  const readsAResponse = record.call.fields.some(
    (field) =>
      field.shape === "keyed" &&
      field.entries.some((entry) => fact(entry.facts, "source_path") !== undefined),
  );
  const forward = (recordedAt: string, stopBehaviour: string) => [
    `${INDENT}return ${send}(`,
    ...passing(record.parameters).map((line) => `${INDENT.repeat(2)}${line}`),
    `${INDENT.repeat(2)}${record.recordedAt}=${recordedAt},`,
    `${INDENT.repeat(2)}${behaviour}=${pyString(stopBehaviour)},`,
    `${INDENT})`,
  ];
  return [
    ...signature(
      send,
      [...record.parameters, record.recordedAt, behaviour],
      "RecordUsageResponse",
    ),
    ...guard(plan, uses, record.call),
    ...sdkCall(plan, uses, record.call, OPERATIONS.record.method, [
      `recorded_at=${record.recordedAt},`,
      `stop_behavior=${behaviour},`,
    ]),
    "",
    "",
    ...hash([...COMMENTS.record, ...(readsAResponse ? COMMENTS.response : [])]),
    ...signature(record.name, record.parameters, "RecordUsageResponse"),
    ...forward("None", PYTHON.stopBehaviorRaise),
    "",
    "",
    ...hash(COMMENTS.backfill),
    ...signature(
      record.backfillName,
      [...record.parameters, record.recordedAt],
      "RecordUsageResponse",
    ),
    ...forward(record.recordedAt, PYTHON.stopBehaviorReturn),
  ];
}

// ---------------------------------------------------------------------------
// The module's own helpers
// ---------------------------------------------------------------------------

function client(plan: Plan): string[] {
  const { client: name, clientHolder } = plan.internal;
  return [
    `${plan.internal.logger} = logging.getLogger(${pyString(PYTHON.logger)})`,
    "",
    `${clientHolder} = None`,
    "",
    "",
    ...hash(COMMENTS.client),
    `def ${name}() -> UBBClient:`,
    `${INDENT}global ${clientHolder}`,
    `${INDENT}if ${clientHolder} is None:`,
    `${INDENT.repeat(2)}${clientHolder} = UBBClient(`,
    ...hash(COMMENTS.apiKey, INDENT.repeat(3)),
    `${INDENT.repeat(3)}api_key=os.environ[${pyString(plan.credential.binding.environmentVariable)}],`,
    ...hash(COMMENTS.baseUrl, INDENT.repeat(3)),
    `${INDENT.repeat(3)}base_url=os.environ.get(${pyString(ENVIRONMENT.baseUrl)}) or ` +
      `${pyString(BASE_URL_DEFAULT)},`,
    `${INDENT.repeat(2)})`,
    `${INDENT}return ${clientHolder}`,
  ];
}

function notReadyHelpers(plan: Plan): string[] {
  const { notReady, notConfigured: unset } = plan.internal;
  const error = PYTHON.notReadyError;
  return [
    ...hash(COMMENTS.notReady),
    `class ${error}(RuntimeError):`,
    `${INDENT}pass`,
    "",
    "",
    `def ${notReady}(operation, readiness, *missing) -> NoReturn:`,
    `${INDENT}detail = "".join(f" {name} ${MESSAGES.notConfigured}." for name in missing)`,
    `${INDENT}raise ${error}(`,
    `${INDENT.repeat(2)}f"{operation} ({readiness}) ${MESSAGES.notReady}{detail}"`,
    `${INDENT})`,
    "",
    "",
    `def ${unset}(name) -> NoReturn:`,
    `${INDENT}raise ${error}(f"{name} ${MESSAGES.notConfigured}.")`,
  ];
}

function reportedCostHelpers(plan: Plan): string[] {
  const { toMicros, pinCurrency, minorUnit } = plan.internal;
  const amount = PYTHON.amountRefused;
  const currency = PYTHON.currencyRefused;
  const table = Object.entries(MICROS_PER_MINOR_UNIT)
    .map(([code, micros]) => `${INDENT}${pyString(code)}: ${micros},`)
    .sort();
  const [micros, minor, major] = AMOUNT_REPRESENTATIONS;
  const i2 = INDENT.repeat(2);
  const i3 = INDENT.repeat(3);
  const i4 = INDENT.repeat(4);
  return [
    ...hash(COMMENTS.reportedCost),
    `class ${amount}(ValueError):`,
    `${INDENT}pass`,
    "",
    "",
    `class ${currency}(ValueError):`,
    `${INDENT}pass`,
    "",
    "",
    "_MICROS_PER_MAJOR_UNIT = 1000000",
    "_MICROS_PER_MINOR_UNIT = {",
    ...table,
    "}",
    "_MICROS_LIMIT = 2 ** 63 - 1",
    "_EXPONENT_LIMIT = 40",
    "",
    "",
    `def ${minorUnit}(currency):`,
    `${INDENT}try:`,
    `${i2}return _MICROS_PER_MINOR_UNIT[currency.lower()]`,
    `${INDENT}except (AttributeError, KeyError):`,
    `${i2}raise ${currency}(`,
    `${i3}f"{currency!r} ${MESSAGES.currencyUnknown}"`,
    `${i2}) from None`,
    "",
    "",
    `def ${pinCurrency}(declared, reported):`,
    `${INDENT}pinned = (declared or "").strip().lower()`,
    `${INDENT}supplied = (reported or "").strip().lower()`,
    `${INDENT}if not pinned and not supplied:`,
    `${i2}raise ${currency}(`,
    `${i3}${pyString(MESSAGES.currencyNone)}`,
    `${i2})`,
    `${INDENT}if pinned and supplied and pinned != supplied:`,
    `${i2}raise ${currency}(`,
    `${i3}f"${MESSAGES.currencyDisagrees}: {supplied!r}, not {pinned!r}"`,
    `${i2})`,
    `${INDENT}code = pinned or supplied`,
    `${INDENT}${minorUnit}(code)`,
    `${INDENT}return code`,
    "",
    "",
    `def ${toMicros}(amount, representation, currency):`,
    `${INDENT}if representation == ${pyString(micros)}:`,
    `${i2}multiplier = 1`,
    `${INDENT}elif representation == ${pyString(minor)}:`,
    `${i2}multiplier = ${minorUnit}(currency)`,
    `${INDENT}elif representation == ${pyString(major)}:`,
    `${i2}multiplier = _MICROS_PER_MAJOR_UNIT`,
    `${INDENT}else:`,
    `${i2}raise ${amount}(`,
    `${i3}f"{representation!r} ${MESSAGES.representation}"`,
    `${i2})`,
    `${INDENT}if isinstance(amount, bool):`,
    `${i2}raise ${amount}(`,
    `${i3}f"{amount!r} ${MESSAGES.flag}"`,
    `${i2})`,
    `${INDENT}if isinstance(amount, float):`,
    `${i2}raise ${amount}(`,
    `${i3}f"{amount!r} ${MESSAGES.float}"`,
    `${i2})`,
    `${INDENT}if amount is None:`,
    `${i2}raise ${amount}(`,
    `${i3}${pyString(MESSAGES.missing)}`,
    `${i2})`,
    `${INDENT}try:`,
    `${i2}exact = Decimal(amount)`,
    `${INDENT}except (InvalidOperation, TypeError, ValueError):`,
    `${i2}raise ${amount}(`,
    `${i3}f"{amount!r} ${MESSAGES.notANumber}"`,
    `${i2}) from None`,
    `${INDENT}if not exact.is_finite():`,
    `${i2}raise ${amount}(`,
    `${i3}f"{amount!r} ${MESSAGES.notFinite}"`,
    `${i2})`,
    `${INDENT}sign, digits, exponent = exact.as_tuple()`,
    `${INDENT}digits = list(digits)`,
    `${INDENT}while exponent < 0 and len(digits) > 1 and digits[-1] == 0:`,
    `${i2}digits.pop()`,
    `${i2}exponent += 1`,
    `${INDENT}unsigned = 0`,
    `${INDENT}for digit in digits:`,
    `${i2}unsigned = unsigned * 10 + digit`,
    `${INDENT}if abs(exponent) > _EXPONENT_LIMIT:`,
    `${i2}raise ${amount}(`,
    `${i3}f"{amount!r} ${MESSAGES.exponent}"`,
    `${i2})`,
    `${INDENT}if exponent >= 0:`,
    `${i2}micros = unsigned * 10 ** exponent * multiplier`,
    `${INDENT}else:`,
    `${i2}micros, remainder = divmod(unsigned * multiplier, 10 ** -exponent)`,
    `${i2}if remainder:`,
    `${i3}raise ${amount}(`,
    `${i4}f"{amount!r} ${MESSAGES.fractional}"`,
    `${i3})`,
    `${INDENT}if micros > _MICROS_LIMIT:`,
    `${i2}raise ${amount}(`,
    `${i3}f"{amount!r} ${MESSAGES.tooLarge}"`,
    `${i2})`,
    `${INDENT}return -micros if sign else micros`,
  ];
}

// ---------------------------------------------------------------------------
// The module
// ---------------------------------------------------------------------------

function section(...blocks: (readonly string[])[]): string[] {
  return blocks.flatMap((block) => (block.length === 0 ? [] : ["", "", ...block]));
}

/** The module's text, and the names it exports. */
export function renderModule(plan: Plan): string {
  const uses: Uses = { notReady: false, reportedCost: false, attribute: false };

  const pricingMode = factOfField(plan.start.call, "task_type", "pricing_mode");
  const sold = typeof pricingMode === "string" ? (PRICING_MODE_COMMENTS[pricingMode] ?? []) : [];
  const start = startFunction(plan, uses, plan.start, [...COMMENTS.start, ...sold]);
  const subtasks = plan.subtasks.map((subtask) =>
    startFunction(plan, uses, subtask, COMMENTS.subtask),
  );
  const records = plan.records.map((record) => recordFunctions(plan, uses, record));

  const exported = [
    ...(uses.reportedCost ? [PYTHON.amountRefused, PYTHON.currencyRefused] : []),
    ...(uses.notReady ? [PYTHON.notReadyError] : []),
    PYTHON.startTask,
    PYTHON.unitOfWork,
    ...plan.subtasks.map((subtask) => subtask.name),
    ...plan.records.flatMap((record) => [record.name, record.backfillName]),
  ];
  const typing = ["Iterator", ...(uses.notReady ? ["NoReturn"] : [])];

  const lines = [
    ...header(plan),
    "",
    "from __future__ import annotations",
    "",
    "import logging",
    "import os",
    "from contextlib import contextmanager",
    ...(uses.reportedCost ? ["from decimal import Decimal, InvalidOperation"] : []),
    `from typing import ${typing.join(", ")}`,
    "",
    "from ubb import RecordUsageResponse, StartedTask, UBBClient, UBBStopRequested",
    "",
    "__all__ = [",
    ...exported.map((name) => `${INDENT}${pyString(name)},`),
    "]",
    "",
    ...client(plan),
    ...(uses.attribute ? ["", "", `${plan.internal.attribute} = getattr`] : []),
    ...section(
      uses.notReady ? notReadyHelpers(plan) : [],
      uses.reportedCost ? reportedCostHelpers(plan) : [],
      start,
      [`${plan.internal.startTask} = ${PYTHON.startTask}`],
      unitOfWork(plan),
      ...subtasks,
      ...records,
    ),
  ];
  return `${lines.join("\n")}\n`;
}
