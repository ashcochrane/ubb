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
 */
import type { Json } from "../blueprint.ts";
import { COMMENTS, MESSAGES } from "../catalogue.ts";
import { hash, statement, tokenStatement } from "../comments.ts";
import { literalOf, type Call, type Entry } from "../tokens.ts";
import type { Plan } from "./plan.ts";
import { pyLiteral, pyString } from "./syntax.ts";

const INDENT = "    ";

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
          const path = entry.facts.find((fact) => fact.element === "source_path");
          return path === undefined
            ? []
            : [{ entry, path: path.token.binding.value, statement: tokenStatement(path.token) }];
        }),
  );
}

function declaredPaths(plan: Plan): string[] {
  const lines: string[] = [];
  for (const record of plan.records) {
    const eventType = literalOf(record.call, "event_type");
    const found = reads(record.call);
    if (typeof eventType !== "string" || found.length === 0) continue;
    lines.push(`${INDENT}${pyString(eventType)}: {`);
    for (const read of found) {
      lines.push(
        ...hash([read.statement], INDENT.repeat(2)),
        `${INDENT.repeat(2)}${pyString(read.entry.keyText)}: ${pyLiteral(read.path)},`,
      );
    }
    lines.push(`${INDENT}},`);
  }
  return lines;
}

export function renderVerifyScript(plan: Plan): string {
  const fingerprint = plan.blueprint.configuration_fingerprint ?? null;
  const say = (message: string) => pyString(message);
  const lines = [
    ...hash(COMMENTS.verify),
    ...hash([statement("configuration_fingerprint", fingerprint)]),
    "",
    "import json",
    "import sys",
    "",
    ...hash(COMMENTS.verifyPaths),
    "DECLARED_PATHS = {",
    ...declaredPaths(plan),
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
    "def main(arguments) -> int:",
    `${INDENT}if not DECLARED_PATHS:`,
    `${INDENT.repeat(2)}print(${say(MESSAGES.verifyNothing)})`,
    `${INDENT.repeat(2)}return 0`,
    `${INDENT}if len(arguments) != 3 or arguments[1] not in DECLARED_PATHS:`,
    `${INDENT.repeat(2)}print(${say(MESSAGES.verifyUsage)})`,
    `${INDENT.repeat(2)}print(${say(MESSAGES.verifyEventTypes)})`,
    `${INDENT.repeat(2)}for event_type in DECLARED_PATHS:`,
    `${INDENT.repeat(3)}print(f"  {json.dumps(event_type, ensure_ascii=False)}")`,
    `${INDENT.repeat(2)}return 2`,
    `${INDENT}declared = DECLARED_PATHS[arguments[1]]`,
    `${INDENT}with open(arguments[2], encoding="utf-8") as captured:`,
    `${INDENT.repeat(2)}document = json.load(captured)`,
    `${INDENT}failures = 0`,
    "",
    `${INDENT}def check(passed, quantity, message):`,
    `${INDENT.repeat(2)}nonlocal failures`,
    `${INDENT.repeat(2)}failures += 0 if passed else 1`,
    `${INDENT.repeat(2)}verdict = "ok  " if passed else "FAIL"`,
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
