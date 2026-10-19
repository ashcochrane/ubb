/**
 * The module: the one file a tenant drops in and never edits.
 *
 * Everything a tenant's running code needs of what the Blueprint resolved is
 * in here — every literal, every declared path, every fact stated beside the
 * value it is about — and none of it is in a call-site block. So when
 * configuration changes, regenerating replaces this file (and the verify
 * script beside it) and touches no line the tenant maintains.
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
 * - `source_path` under a keyed entry, or — since renderer contract 2 (#583)
 *   — on a field of its own: the value is read off the parameter by that
 *   path, and `response_shape_representation` on the call's Event Type says
 *   how — by subscript for JSON, by attribute for a Python object. A segment
 *   is only ever written as itself; one Python cannot spell as an attribute
 *   is reached with `getattr`, which changes the syntax and not the name.
 *   With no representation there is no way to read the path, and the value
 *   is written as a call that raises. The fields read this way are a
 *   supplier's cost and its currency; any other is refused.
 * - `amount_representation` on a field: the value is a supplier's cost —
 *   the caller's own, or one read off the response — converted to whole
 *   micros once, in the currency the call's `currency` field pins or reads.
 * - `pricing_mode` on the kind of work: which sentence says what delivering
 *   the work does.
 */
import { refuse, type Json } from "../blueprint.ts";
import {
  AMOUNT_REPRESENTATION,
  COMMENTS,
  ENVIRONMENT,
  MESSAGES,
  MICROS_PER_MINOR_UNIT,
  PRICING_MODE_COMMENTS,
  PYTHON,
  READINESS_COMMENTS,
  RESPONSE_REPRESENTATION,
} from "../catalogue.ts";
import { asComments, tokenStatement } from "../comments.ts";
import { headerText } from "../header.ts";
import {
  factNamed,
  factOfField,
  literalOf,
  notWritten,
  said,
  SAID_OF,
  type Call,
  type Entry,
  type Field,
  type KeyedField,
  type Literal,
  type NotRenderable,
  type Parameter,
  type ScalarField,
  type Token,
  type Unconfigured,
} from "../tokens.ts";
import {
  FACT,
  FIELD,
  OPERATIONS,
  STOP_FIELDS,
  type Plan,
  type RecordPlan,
  type StartPlan,
} from "./plan.ts";
import { INDENT, isIdentifier, pyLiteral, pyString, unshadowed } from "./syntax.ts";

/** What the module turned out to need, found while writing its calls. */
interface Uses {
  notReady: boolean;
  /** Each of the two values a call can be written without, which decides
   * which of their helpers the module carries. */
  notConfigured: boolean;
  notRenderable: boolean;
  reportedCost: boolean;
  /** A cost the caller passes, which the comments speak to (#577). */
  callerCost: boolean;
  /** A supplier's cost, or its currency, read off the response (#583). */
  responseRead: boolean;
  /** A currency read off the response, which needs a helper of its own. */
  currencyRead: boolean;
  attribute: boolean;
}

/** Which costs a file converts, which decides the words and helpers it
 * carries beside the conversion. */
export interface CostsConverted {
  callerCost: boolean;
  currencyRead: boolean;
}

// ---------------------------------------------------------------------------
// The header
// ---------------------------------------------------------------------------

function header(plan: Plan): string[] {
  return headerText(plan.header, plan.calls, READINESS_COMMENTS, COMMENTS.legend).map((line) =>
    line === "" ? "" : `# ${line}`,
  );
}

// ---------------------------------------------------------------------------
// Values
// ---------------------------------------------------------------------------

type Valued = Token<Literal | Unconfigured | NotRenderable | Parameter>;

function notConfigured(plan: Plan, uses: Uses, name: string): string {
  uses.notReady = true;
  uses.notConfigured = true;
  return `${plan.internal.notConfigured}(${pyString(name)})`;
}

/** A declared value this Code Builder version cannot yet generate (#571), in
 * its place as a call that raises saying so — never as one that calls it
 * missing. */
function notRenderable(plan: Plan, uses: Uses, name: string): string {
  uses.notReady = true;
  uses.notRenderable = true;
  return `${plan.internal.notRenderable}(${pyString(name)})`;
}

function plain(plan: Plan, uses: Uses, token: Valued): string {
  switch (token.binding.kind) {
    case "literal":
      return pyLiteral(token.binding.value);
    case "parameter":
      return token.binding.name;
    case "unconfigured":
      return notConfigured(plan, uses, token.name);
    case "not_renderable":
      return notRenderable(plan, uses, token.name);
  }
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
  if (representation === RESPONSE_REPRESENTATION.json) {
    return root + segments.map((segment) => `[${pyString(segment)}]`).join("");
  }
  if (representation === RESPONSE_REPRESENTATION.pythonObject) {
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
  const path = factNamed(entry.facts, FACT.sourcePath);
  if (path !== undefined && entry.value.binding.kind === "parameter") {
    const read = traversal(
      plan,
      uses,
      entry.value.binding.name,
      path,
      factOfField(call, FIELD.eventType, FACT.responseRepresentation),
    );
    return read ?? notConfigured(plan, uses, entry.value.name);
  }
  return plain(plan, uses, entry.value);
}

/**
 * A scalar field's value read off the parameter it names, by its declared
 * `source_path` (renderer contract 2, #583): `undefined` where it declares
 * none, and `null` where this target has no way to read the response's
 * representation.
 */
function readOff(plan: Plan, uses: Uses, call: Call, field: ScalarField): string | null | undefined {
  const path = factNamed(field.facts, FACT.sourcePath);
  if (path === undefined) return undefined;
  if (field.token.binding.kind !== "parameter") {
    return refuse(`${field.name} declares a path and is not a value read at run time`);
  }
  uses.responseRead = true;
  return traversal(
    plan,
    uses,
    field.token.binding.name,
    path,
    factOfField(call, FIELD.eventType, FACT.responseRepresentation),
  );
}

/** The currency a call's cost is converted in: the one it pins, the one read
 * off the response, or none — which the helper then refuses. */
function costCurrency(plan: Plan, uses: Uses, call: Call): string {
  const { pinCurrency, readCurrency } = plan.internal;
  const currency = call.fields.find(
    (field): field is ScalarField => field.shape === "scalar" && field.name === FIELD.currency,
  );
  const read = currency === undefined ? undefined : readOff(plan, uses, call, currency);
  if (read !== undefined) {
    if (read === null) return notConfigured(plan, uses, currency!.token.name);
    uses.currencyRead = true;
    return `${pinCurrency}("", ${readCurrency}(${read}))`;
  }
  const declared = literalOf(call, FIELD.currency);
  return `${pinCurrency}(${pyLiteral(typeof declared === "string" ? declared : "")}, None)`;
}

function scalarValue(plan: Plan, uses: Uses, call: Call, field: ScalarField): string {
  const representation = factNamed(field.facts, FACT.amountRepresentation);
  const read = readOff(plan, uses, call, field);
  if (representation !== undefined && field.token.binding.kind === "parameter") {
    if (!(Object.values(AMOUNT_REPRESENTATION) as Json[]).includes(representation)) {
      refuse(`${String(representation)} is not an amount representation this target converts`);
    }
    uses.reportedCost = true;
    if (read === null) return notConfigured(plan, uses, field.token.name);
    if (read === undefined) uses.callerCost = true;
    // A cost read off the response is refused as a float in words that say
    // what to read instead; the conversion is the caller's cost's own.
    const amount =
      read === undefined ? field.token.binding.name : `${plan.internal.readAmount}(${read})`;
    return (
      `${plan.internal.toMicros}(${amount}, ${pyLiteral(representation)}, ` +
      `${costCurrency(plan, uses, call)})`
    );
  }
  if (read !== undefined) {
    // The one other value read off the response is the currency the cost
    // beside it is in: pinned to a code UBB holds, and sent as the event's.
    if (field.name !== FIELD.currency) {
      refuse(
        `${field.name} is read off the response, and this target reads only a ` +
          `supplier's cost and its currency that way`,
      );
    }
    uses.reportedCost = true;
    return costCurrency(plan, uses, call);
  }
  return plain(plan, uses, field.token);
}

// ---------------------------------------------------------------------------
// A call to the SDK
// ---------------------------------------------------------------------------

/** The provenance comment of each literal among `tokens`, in order. */
function provenanceComments(tokens: readonly Token[], indent: string): string[] {
  return asComments(
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
      ...provenanceComments(
        [field.token, ...field.facts.map((declared) => declared.token)],
        indent,
      ),
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
      ...provenanceComments(
        [entry.key, ...entry.facts.map((declared) => declared.token)],
        indent,
      ),
      // A key no token gives a value to is stated and not sent.
      ...(value === null ? [] : [`${indent}${pyString(entry.keyText)}: ${value},`]),
    ];
  });
}

function guard(plan: Plan, uses: Uses, call: Call): string[] {
  if (call.readiness === "complete") return [];
  uses.notReady = true;
  // Each value the Blueprint leaves the call without, said as what is true
  // of it: one nothing configures, or one the tenant declared and this Code
  // Builder version cannot yet generate. The sentence is made here, so the
  // helper that raises states no reason of its own.
  const reasons = notWritten(call)
    .map((value) => `, ${pyString(said(value))}`)
    .join("");
  return [
    ...asComments(COMMENTS.notReadyCall, INDENT),
    `${INDENT}${plan.internal.notReady}(${pyString(call.operationId)}, ` +
      `${pyString(call.readiness)}${reasons})`,
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
    ...asComments(comments),
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
  const task = unshadowed("task", taken);
  const stop = unshadowed("stop", taken);
  const inner = INDENT.repeat(3);
  return [
    ...asComments(COMMENTS.unitOfWork),
    "@contextmanager",
    ...signature(PYTHON.unitOfWork, start.parameters, "Iterator[StartedTask]"),
    `${INDENT}try:`,
    `${INDENT.repeat(2)}with ${plan.internal.startTask}(`,
    ...passing(start.parameters).map((line) => `${inner}${line}`),
    `${INDENT.repeat(2)}) as ${task}:`,
    `${inner}yield ${task}`,
    `${INDENT}except UBBStopRequested as ${stop}:`,
    // The key the event was sent under, and each field the stop is
    // explained by, BY ITS OWN NAME, read straight off what was caught
    // (ADR-0016 §4; the owner's ruling on #577): never the acknowledgement's
    // own description of itself, and nothing worked out from any field.
    `${INDENT.repeat(2)}${plan.internal.logger}.warning(`,
    `${inner}${pyString(MESSAGES.stop)},`,
    `${inner}${stop}.idempotency_key,`,
    ...STOP_FIELDS.map((name) => `${inner}${stop}.${name},`),
    `${INDENT.repeat(2)})`,
    `${INDENT.repeat(2)}raise`,
  ];
}

function recordFunctions(plan: Plan, uses: Uses, record: RecordPlan): string[] {
  const send = plan.internal.send(record);
  const behaviour = unshadowed(
    "stop_behavior",
    new Set([...record.parameters, record.recordedAt]),
  );
  const readsAResponse = record.call.fields.some((field) =>
    field.shape === "keyed"
      ? field.entries.some((entry) => factNamed(entry.facts, FACT.sourcePath) !== undefined)
      : factNamed(field.facts, FACT.sourcePath) !== undefined,
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
    ...asComments([...COMMENTS.record, ...(readsAResponse ? COMMENTS.response : [])]),
    ...signature(record.name, record.parameters, "RecordUsageResponse"),
    ...forward("None", PYTHON.stopBehaviorRaise),
    "",
    "",
    ...asComments(COMMENTS.backfill),
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
    ...asComments(COMMENTS.environmentNotSet),
    `class ${PYTHON.environmentError}(RuntimeError):`,
    `${INDENT}pass`,
    "",
    "",
    ...asComments(COMMENTS.client),
    `def ${name}() -> UBBClient:`,
    `${INDENT}global ${clientHolder}`,
    `${INDENT}if ${clientHolder} is None:`,
    // Where the API is, is read and never defaulted: an unset or an empty
    // variable refuses here, before any client exists to send anything.
    ...asComments(COMMENTS.baseUrl, INDENT.repeat(2)),
    `${INDENT.repeat(2)}base_url = os.environ.get(${pyString(ENVIRONMENT.baseUrl)})`,
    `${INDENT.repeat(2)}if not base_url:`,
    `${INDENT.repeat(3)}raise ${PYTHON.environmentError}(`,
    `${INDENT.repeat(4)}${pyString(`${ENVIRONMENT.baseUrl} ${MESSAGES.environmentNotSet}`)}`,
    `${INDENT.repeat(3)})`,
    `${INDENT.repeat(2)}${clientHolder} = UBBClient(`,
    ...asComments(COMMENTS.apiKey, INDENT.repeat(3)),
    `${INDENT.repeat(3)}api_key=os.environ[${pyString(plan.credential.binding.environmentVariable)}],`,
    `${INDENT.repeat(3)}base_url=base_url,`,
    `${INDENT.repeat(2)})`,
    `${INDENT}return ${clientHolder}`,
  ];
}

function notReadyHelpers(plan: Plan, uses: Uses): string[] {
  const { notReady, notConfigured: unset, notRenderable: unrenderable } = plan.internal;
  const error = PYTHON.notReadyError;
  return [
    ...asComments(COMMENTS.notReady),
    `class ${error}(RuntimeError):`,
    `${INDENT}pass`,
    "",
    "",
    `def ${notReady}(operation, readiness, *reasons) -> NoReturn:`,
    `${INDENT}detail = "".join(f" {reason}" for reason in reasons)`,
    `${INDENT}raise ${error}(`,
    `${INDENT.repeat(2)}f"{operation} ({readiness}) ${MESSAGES.notReady}{detail}"`,
    `${INDENT})`,
    ...(uses.notConfigured
      ? ["", "", `def ${unset}(name) -> NoReturn:`, `${INDENT}raise ${error}(f"{name} ${SAID_OF.unconfigured}.")`]
      : []),
    ...(uses.notRenderable
      ? ["", "", `def ${unrenderable}(name) -> NoReturn:`, `${INDENT}raise ${error}(f"{name} ${SAID_OF.not_renderable}.")`]
      : []),
  ];
}

/**
 * What a value read off the response passes through before the conversion
 * every reported cost shares: a float is refused in words that say what to
 * read instead, and — where the file reads one — a currency that is not text
 * is refused before it is pinned. Everything else is the caller's cost's own
 * rule, unchanged.
 */
export function responseReadHelpers(plan: Plan, costs: CostsConverted): string[] {
  const { readAmount, readCurrency } = plan.internal;
  const i2 = INDENT.repeat(2);
  return [
    ...asComments([...COMMENTS.responseCost, ...(costs.currencyRead ? COMMENTS.responseCurrency : [])]),
    `def ${readAmount}(amount):`,
    `${INDENT}if isinstance(amount, float):`,
    `${i2}raise ${PYTHON.amountRefused}(`,
    `${INDENT.repeat(3)}f"{amount!r} ${MESSAGES.floatRead}"`,
    `${i2})`,
    `${INDENT}return amount`,
    ...(costs.currencyRead
      ? [
          "",
          "",
          `def ${readCurrency}(currency):`,
          `${INDENT}if not isinstance(currency, str):`,
          `${i2}raise ${PYTHON.currencyRefused}(`,
          `${INDENT.repeat(3)}f"{currency!r} ${MESSAGES.currencyNotText}"`,
          `${i2})`,
          `${INDENT}return currency`,
        ]
      : []),
  ];
}

export function reportedCostHelpers(plan: Plan, costs: CostsConverted): string[] {
  const { toMicros, pinCurrency, minorUnit } = plan.internal;
  const amount = PYTHON.amountRefused;
  const currency = PYTHON.currencyRefused;
  const table = Object.entries(MICROS_PER_MINOR_UNIT)
    .map(([code, micros]) => `${INDENT}${pyString(code)}: ${micros},`)
    .sort();
  const { micros, minorUnits: minor, majorUnitsDecimal: major } = AMOUNT_REPRESENTATION;
  const i2 = INDENT.repeat(2);
  const i3 = INDENT.repeat(3);
  const i4 = INDENT.repeat(4);
  return [
    ...asComments([...COMMENTS.reportedCost, ...(costs.callerCost ? COMMENTS.callerCost : [])]),
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

/** The module's text. */
export function renderModule(plan: Plan): string {
  const uses: Uses = {
    notReady: false,
    notConfigured: false,
    notRenderable: false,
    reportedCost: false,
    callerCost: false,
    responseRead: false,
    currencyRead: false,
    attribute: false,
  };

  const pricingMode = factOfField(plan.start.call, FIELD.kindOfWork, FACT.pricingMode);
  const sold = typeof pricingMode === "string" ? (PRICING_MODE_COMMENTS[pricingMode] ?? []) : [];
  const start = startFunction(plan, uses, plan.start, [...COMMENTS.start, ...sold]);
  const subtasks = plan.subtasks.map((subtask) =>
    startFunction(plan, uses, subtask, COMMENTS.subtask),
  );
  const records = plan.records.map((record) => recordFunctions(plan, uses, record));

  const exported = [
    PYTHON.environmentError,
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
      uses.notReady ? notReadyHelpers(plan, uses) : [],
      uses.reportedCost ? reportedCostHelpers(plan, uses) : [],
      uses.responseRead ? responseReadHelpers(plan, uses) : [],
      start,
      [`${plan.internal.startTask} = ${PYTHON.startTask}`],
      unitOfWork(plan),
      ...subtasks,
      ...records,
    ),
  ];
  return `${lines.join("\n")}\n`;
}
