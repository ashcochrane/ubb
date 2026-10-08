/**
 * The verify script: the declared paths, checked against a response the
 * tenant's supplier really returned.
 *
 * UBB never sees a supplier's response, so it cannot tell a path that reads
 * the right field from one that reads a neighbouring one: both satisfy every
 * check the platform has. This script is the one place that is checked, and
 * only the tenant can run it. It reads a captured response from a file and
 * calls nothing — no supplier, and no UBB.
 *
 * It catches the three signatures of a wrong path: a path that resolves to
 * nothing, a quantity that reads a constant zero, and two quantities reading
 * one field. A segment is looked up as the key it was declared as, whichever
 * way the module reads the live object.
 *
 * A SUPPLIER'S COST READ OFF THE RESPONSE (#583) is checked by STRUCTURE and
 * never by its size, because a cost of zero is a cost (owner's ruling 5 on
 * #583): its path resolves, what is there is an integer or a decimal string,
 * the currency read beside it (where one is) resolves and is one UBB holds,
 * and the amount converts to whole micros exactly — by the module's own
 * conversion, written into this script from the same text.
 */
import type { Json } from "../blueprint.ts";
import { COMMENTS, MESSAGES, PYTHON } from "../catalogue.ts";
import { asComments, statement, tokenStatement } from "../comments.ts";
import {
  factNamed,
  literalOf,
  type Call,
  type Entry,
  type Fact,
  type Literal,
  type ScalarField,
  type Token,
} from "../tokens.ts";
import { reportedCostHelpers, responseReadHelpers } from "./module.ts";
import { FACT, FIELD, type Plan } from "./plan.ts";
import { INDENT, pyLiteral, pyString } from "./syntax.ts";

interface Read {
  readonly entry: Entry;
  readonly path: Json;
  readonly statement: string;
}

function reads(call: Call): Read[] {
  return call.fields.flatMap((field) =>
    field.shape !== "keyed"
      ? []
      : field.entries.flatMap((entry) => {
          const path = entry.facts.find((fact) => fact.element === FACT.sourcePath);
          return path === undefined
            ? []
            : [{ entry, path: path.token.binding.value, statement: tokenStatement(path.token) }];
        }),
  );
}

function declaredPaths(plan: Plan): string[] {
  const lines: string[] = [];
  for (const record of plan.records) {
    const eventType = literalOf(record.call, FIELD.eventType);
    const found = reads(record.call);
    if (typeof eventType !== "string" || found.length === 0) continue;
    lines.push(`${INDENT}${pyString(eventType)}: {`);
    for (const read of found) {
      lines.push(
        ...asComments([read.statement], INDENT.repeat(2)),
        `${INDENT.repeat(2)}${pyString(read.entry.keyText)}: ${pyLiteral(read.path)},`,
      );
    }
    lines.push(`${INDENT}},`);
  }
  return lines;
}

/** A supplier's cost one call reads off the response, and the currency
 * beside it, as declared. */
interface CostRead {
  readonly eventType: string;
  readonly cost: ScalarField;
  readonly path: Fact;
  readonly representation: Fact;
  readonly currency: ScalarField | undefined;
  readonly currencyPath: Fact | undefined;
}

function scalar(call: Call, name: string): ScalarField | undefined {
  return call.fields.find(
    (field): field is ScalarField => field.shape === "scalar" && field.name === name,
  );
}

/** The declared fact itself, token and all — `tokens.factNamed` answers its
 * value alone, and the script states each fact's provenance beside it. */
function fact(facts: readonly Fact[], element: string): Fact | undefined {
  return facts.find((declared) => declared.element === element);
}

/** Every record whose supplier's cost is read off the response. */
function costReads(plan: Plan): CostRead[] {
  return plan.records.flatMap((record) => {
    const eventType = literalOf(record.call, FIELD.eventType);
    const cost = record.call.fields.find(
      (field): field is ScalarField =>
        field.shape === "scalar" &&
        factNamed(field.facts, FACT.amountRepresentation) !== undefined &&
        factNamed(field.facts, FACT.sourcePath) !== undefined,
    );
    if (typeof eventType !== "string" || cost === undefined) return [];
    const currency = scalar(record.call, FIELD.currency);
    return [
      {
        eventType,
        cost,
        path: fact(cost.facts, FACT.sourcePath)!,
        representation: fact(cost.facts, FACT.amountRepresentation)!,
        currency,
        currencyPath: currency === undefined ? undefined : fact(currency.facts, FACT.sourcePath),
      },
    ];
  });
}

function pinnedCurrency(currency: ScalarField | undefined): Token<Literal> | undefined {
  const token = currency?.token;
  return token !== undefined && token.binding.kind === "literal"
    ? (token as Token<Literal>)
    : undefined;
}

function declaredCosts(found: readonly CostRead[]): string[] {
  const i2 = INDENT.repeat(2);
  return found.flatMap((read) => {
    const pinned = pinnedCurrency(read.currency);
    return [
      `${INDENT}${pyString(read.eventType)}: {`,
      ...asComments([tokenStatement(read.path.token)], i2),
      `${i2}"source_path": ${pyLiteral(read.path.token.binding.value)},`,
      ...asComments([tokenStatement(read.representation.token)], i2),
      `${i2}"amount_representation": ${pyLiteral(read.representation.token.binding.value)},`,
      ...(pinned === undefined ? [] : asComments([tokenStatement(pinned)], i2)),
      `${i2}"currency": ${pyLiteral(pinned === undefined ? "" : pinned.binding.value)},`,
      ...(read.currencyPath === undefined ? [] : asComments([tokenStatement(read.currencyPath.token)], i2)),
      `${i2}"currency_path": ${read.currencyPath === undefined ? "None" : pyLiteral(read.currencyPath.token.binding.value)},`,
      `${INDENT}},`,
    ];
  });
}

/** The checks of one supplier's cost, by structure alone; with the currency
 * read beside it only where some mapping reads one. */
function costCheck(plan: Plan, found: readonly CostRead[], readsCurrency: boolean): string[] {
  const { pinCurrency, readAmount, readCurrency, toMicros } = plan.internal;
  const [i1, i2, i3] = [INDENT, INDENT.repeat(2), INDENT.repeat(3)];
  const say = pyString;
  // Every cost read off a response fills the one field the platform names
  // for that source, so the first record's name is every record's.
  return [
    `COST = ${pyString(found[0]!.cost.name)}`,
    ...(readsCurrency ? [`CURRENCY = ${pyString(FIELD.currency)}`] : []),
    "",
    "",
    "def _check_cost(cost, document, check):",
    `${i1}amount = _resolve(document, cost["source_path"])`,
    `${i1}check(amount is not _MISSING, COST, ${say(MESSAGES.verifyResolves)})`,
    `${i1}admissible = isinstance(amount, (int, str)) and not isinstance(amount, bool)`,
    `${i1}if amount is not _MISSING:`,
    `${i2}check(admissible, COST, ${say(MESSAGES.verifyAmount)})`,
    ...(readsCurrency
      ? [
          `${i1}supplied = None`,
          `${i1}if cost["currency_path"] is not None:`,
          `${i2}supplied = _resolve(document, cost["currency_path"])`,
          `${i2}check(supplied is not _MISSING, CURRENCY, ${say(MESSAGES.verifyResolves)})`,
          `${i2}if supplied is _MISSING:`,
          `${i3}return`,
          `${i1}try:`,
          `${i2}currency = ${pinCurrency}(`,
          `${i3}cost["currency"], None if supplied is None else ${readCurrency}(supplied))`,
          `${i1}except ${PYTHON.currencyRefused}:`,
          `${i2}currency = None`,
          `${i1}if cost["currency_path"] is not None:`,
          `${i2}check(currency is not None, CURRENCY, ${say(MESSAGES.verifyCurrency)})`,
        ]
      : [
          `${i1}try:`,
          `${i2}currency = ${pinCurrency}(cost["currency"], None)`,
          `${i1}except ${PYTHON.currencyRefused}:`,
          `${i2}currency = None`,
        ]),
    `${i1}if admissible and currency is not None:`,
    `${i2}try:`,
    `${i3}${toMicros}(${readAmount}(amount), cost["amount_representation"], currency)`,
    `${i3}converts = True`,
    `${i2}except (${PYTHON.amountRefused}, ${PYTHON.currencyRefused}):`,
    `${i3}converts = False`,
    `${i2}check(converts, COST, ${say(MESSAGES.verifyConverts)})`,
  ];
}

export function renderVerifyScript(plan: Plan): string {
  const fingerprint = plan.header.configuration_fingerprint ?? null;
  const say = pyString;
  const costs = costReads(plan);
  const checksCosts = costs.length > 0;
  const converted = {
    callerCost: false,
    currencyRead: costs.some((read) => read.currencyPath !== undefined),
  };
  const lines = [
    ...asComments(COMMENTS.verify),
    ...asComments([statement("configuration_fingerprint", fingerprint)]),
    "",
    "import json",
    "import sys",
    ...(checksCosts ? ["from decimal import Decimal, InvalidOperation"] : []),
    "",
    ...asComments(COMMENTS.verifyPaths),
    "DECLARED_PATHS = {",
    ...declaredPaths(plan),
    "}",
    "",
    ...asComments(COMMENTS.verifyCosts),
    "DECLARED_COSTS = {",
    ...declaredCosts(costs),
    "}",
    "",
    "_MISSING = object()",
    "",
    "",
    "def _resolve(document, segments):",
    `${INDENT}found = document`,
    `${INDENT}for segment in segments:`,
    `${INDENT.repeat(2)}if not isinstance(found, dict) or segment not in found:`,
    `${INDENT.repeat(3)}return _MISSING`,
    `${INDENT.repeat(2)}found = found[segment]`,
    `${INDENT}return found`,
    "",
    "",
    ...(checksCosts
      ? [
          ...reportedCostHelpers(plan, converted),
          "",
          "",
          ...responseReadHelpers(plan, converted),
          "",
          "",
          ...costCheck(plan, costs, converted.currencyRead),
          "",
          "",
        ]
      : []),
    "def main(arguments) -> int:",
    `${INDENT}known = [*DECLARED_PATHS, *(event_type for event_type in DECLARED_COSTS`,
    `${INDENT}                            if event_type not in DECLARED_PATHS)]`,
    `${INDENT}if not known:`,
    `${INDENT.repeat(2)}print(${say(MESSAGES.verifyNothing)})`,
    `${INDENT.repeat(2)}return 0`,
    `${INDENT}if len(arguments) != 3 or arguments[1] not in known:`,
    `${INDENT.repeat(2)}print(${say(MESSAGES.verifyUsage)})`,
    `${INDENT.repeat(2)}print(${say(MESSAGES.verifyEventTypes)})`,
    `${INDENT.repeat(2)}for event_type in known:`,
    `${INDENT.repeat(3)}print(f"  {json.dumps(event_type, ensure_ascii=False)}")`,
    `${INDENT.repeat(2)}return 2`,
    `${INDENT}declared = DECLARED_PATHS.get(arguments[1], {})`,
    `${INDENT}with open(arguments[2], encoding="utf-8") as captured:`,
    `${INDENT.repeat(2)}document = json.load(captured)`,
    `${INDENT}failures = 0`,
    "",
    `${INDENT}def check(passed, quantity, message):`,
    `${INDENT.repeat(2)}nonlocal failures`,
    `${INDENT.repeat(2)}failures += 0 if passed else 1`,
    `${INDENT.repeat(2)}verdict = ${say(MESSAGES.verifyOk)} if passed else ${say(MESSAGES.verifyFail)}`,
    `${INDENT.repeat(2)}print(f"  {verdict} {json.dumps(quantity, ensure_ascii=False)} {message}")`,
    "",
    `${INDENT}for quantity, segments in declared.items():`,
    `${INDENT.repeat(2)}value = _resolve(document, segments)`,
    `${INDENT.repeat(2)}check(value is not _MISSING, quantity, ${say(MESSAGES.verifyResolves)})`,
    `${INDENT.repeat(2)}if value is _MISSING:`,
    `${INDENT.repeat(3)}continue`,
    `${INDENT.repeat(2)}number = isinstance(value, (int, float)) and not isinstance(value, bool)`,
    `${INDENT.repeat(2)}check(number, quantity, ${say(MESSAGES.verifyNumber)})`,
    `${INDENT.repeat(2)}if number:`,
    `${INDENT.repeat(3)}check(value != 0, quantity, ${say(MESSAGES.verifyNotZero)})`,
    `${INDENT.repeat(2)}shared = [other for other, path in declared.items()`,
    `${INDENT.repeat(2)}          if other != quantity and path == segments]`,
    `${INDENT.repeat(2)}check(not shared, quantity, ${say(MESSAGES.verifyDistinct)})`,
    ...(checksCosts
      ? [
          `${INDENT}if arguments[1] in DECLARED_COSTS:`,
          `${INDENT.repeat(2)}_check_cost(DECLARED_COSTS[arguments[1]], document, check)`,
        ]
      : []),
    "",
    `${INDENT}if failures:`,
    `${INDENT.repeat(2)}print(f"{failures} ${MESSAGES.verifyFailed}")`,
    `${INDENT.repeat(2)}return 1`,
    `${INDENT}print(${say(MESSAGES.verifyPassed)})`,
    `${INDENT}return 0`,
    "",
    "",
    'if __name__ == "__main__":',
    `${INDENT}raise SystemExit(main(sys.argv))`,
  ];
  return `${lines.join("\n")}\n`;
}
