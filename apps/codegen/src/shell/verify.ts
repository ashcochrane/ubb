/**
 * The verify script: the declared paths, checked against a response the
 * tenant's supplier really returned.
 *
 * UBB never sees a supplier's response, so it cannot tell a path that reads
 * the right field from one that reads a neighbouring one: both satisfy every
 * check the platform has. This script is the one place that is checked, and
 * only the tenant can run it. It reads a captured response from a file and
 * calls nothing — no supplier, and no UBB — so it needs jq and not curl.
 *
 * It catches the three signatures of a wrong path: a path that resolves to
 * nothing, a quantity that reads a constant zero, and two quantities reading
 * one field.
 *
 * It is a script that is RUN, not a file that is sourced, so unlike the
 * runnable file it ends with `exit`. Everything it knows of the tenant's
 * declarations is inside one jq program in a quoted heredoc, and everything
 * it prints is that program's output: no declared name is ever shell text.
 */
import { COMMENTS, MESSAGES, SHELL_COMMENTS, SHELL_EXIT, SHELL_FILE, SHELL_MESSAGES } from "../catalogue.ts";
import { asComments, statement } from "../comments.ts";
import { FIELD } from "../lifecycle.ts";
import { literalOf } from "../tokens.ts";
import type { CallPlan, Member, Plan, Value } from "./plan.ts";
import { jqNeedsOf, jqProbe } from "./probe.ts";
import { INDENT, jqLiteral, jqString, shWord } from "./syntax.ts";

const I1 = INDENT;
const I2 = INDENT.repeat(2);
const I3 = INDENT.repeat(3);

type Read = Member & { readonly value: Extract<Value, { kind: "read" }> };

function reads(record: CallPlan): Read[] {
  return record.body.flatMap((field) =>
    field.shape === "keyed"
      ? field.members.filter((member): member is Read => member.value?.kind === "read")
      : [],
  );
}

/** Every quantity read off a response, by Event Type, as one jq object. */
function declaredPaths(plan: Plan): string[] {
  const eventTypes = plan.records.flatMap((record) => {
    const eventType = literalOf(record.call, FIELD.eventType);
    const found = reads(record);
    return typeof eventType === "string" && found.length > 0 ? [{ eventType, found }] : [];
  });
  const lines: string[] = ["{"];
  eventTypes.forEach(({ eventType, found }, index) => {
    lines.push(`${I1}${jqString(eventType)}: {`);
    found.forEach((read, at) => {
      lines.push(
        `${I2}# ${read.value.declared}`,
        `${I2}${jqString(read.key)}: ${jqLiteral(read.value.path)}${at === found.length - 1 ? "" : ","}`,
      );
    });
    lines.push(`${I1}}${index === eventTypes.length - 1 ? "" : ","}`);
  });
  lines.push("} as $declared");
  return lines;
}

export function renderVerifyScript(plan: Plan): string {
  // A line the program prints, as the jq string that is it.
  const say = jqString;
  const unavailable = SHELL_EXIT.toolUnavailable.status;
  const program = [
    ...COMMENTS.verifyPaths.map((line) => `# ${line}`),
    ...declaredPaths(plan),
    "| def resolve($path):",
    `${I2}reduce $path[] as $segment ({"found": true, "at": .};`,
    `${I3}if .found and (.at | type) == "object" and (.at | has($segment))`,
    `${I3}then {"found": true, "at": .at[$segment]}`,
    `${I3}else {"found": false, "at": null} end);`,
    `${I1}def check($passed; $quantity; $message):`,
    `${I2}"  " + (if $passed then ${say(MESSAGES.verifyOk)} else ${say(MESSAGES.verifyFail)} end)`,
    `${I2}+ " " + ($quantity | tojson) + " " + $message;`,
    `${I1}if ($declared | length) == 0`,
    `${I1}then "0", ${say(MESSAGES.verifyNothing)}`,
    `${I1}elif $given != "2" or ($declared | has($event_type) | not)`,
    `${I1}then "2", ${say(SHELL_MESSAGES.verifyUsage)}, ${say(MESSAGES.verifyEventTypes)},`,
    `${I2}($declared | keys_unsorted[] | "  " + tojson)`,
    `${I1}else`,
    `${I2}$declared[$event_type] as $paths`,
    `${I2}| [ $paths | to_entries[] | .key as $quantity | .value as $path`,
    `${I3}| ($captured[0] | resolve($path)) as $resolved`,
    `${I3}| check($resolved.found; $quantity; ${say(MESSAGES.verifyResolves)}),`,
    `${I3}  ( select($resolved.found)`,
    `${I3}    | (($resolved.at | type) == "number") as $number`,
    `${I3}    | check($number; $quantity; ${say(MESSAGES.verifyNumber)}),`,
    `${I3}      ( select($number)`,
    `${I3}        | check($resolved.at != 0; $quantity; ${say(MESSAGES.verifyNotZero)}) ),`,
    `${I3}      check(`,
    `${I3}        ([ $paths | to_entries[] | select(.key != $quantity and .value == $path) ]`,
    `${I3}         | length) == 0;`,
    `${I3}        $quantity; ${say(MESSAGES.verifyDistinct)}) ) ] as $lines`,
    `${I2}| ([ $lines[] | select(startswith("  " + ${say(MESSAGES.verifyFail)})) ] | length) as $failures`,
    `${I2}| if $failures > 0`,
    `${I3}then "1", $lines[], (($failures | tostring) + " " + ${say(MESSAGES.verifyFailed)})`,
    `${I3}else "0", $lines[], ${say(MESSAGES.verifyPassed)} end`,
    `${I1}end`,
  ];

  const refusal = (message: string) => [
    `${I1}printf '%s\\n' ${shWord(message)} >&2`,
    `${I1}exit ${unavailable}`,
  ];
  // The program answers with the status to exit with, then with every line
  // to print. Each line is one line whatever a declared name holds: a name
  // is printed as JSON. It is a function of its own, so that the heredoc is
  // never inside the substitution that captures what it prints.
  const checked = [
    "ubb_checked() {",
    `${I1}jq --raw-output --null-input \\`,
    `${I2}--arg event_type "\${1-}" \\`,
    `${I2}--arg given "$#" \\`,
    `${I2}--slurpfile captured "\${2:-/dev/null}" \\`,
    `${I2}--from-file /dev/stdin <<'${SHELL_FILE.heredoc}'`,
    ...program.map((line) => `${I1}${line}`),
    SHELL_FILE.heredoc,
    "}",
  ];
  const lines = [
    ...asComments(SHELL_COMMENTS.verify),
    ...asComments([statement("configuration_fingerprint", plan.header.configuration_fingerprint ?? null)]),
    "",
    ...asComments(SHELL_COMMENTS.verifyPreflight),
    "command -v jq >/dev/null 2>&1 || {",
    ...refusal(SHELL_MESSAGES.jqMissing),
    "}",
    "ubb_probe=0",
    // For exactly what the one program below asks of jq.
    ...jqProbe("", "ubb_probe", jqNeedsOf(checked.join("\n"))),
    `[ "$ubb_probe" -eq 0 ] || {`,
    ...refusal(SHELL_MESSAGES.jqUnusable),
    "}",
    "",
    ...checked,
    "",
    'ubb_report=$(ubb_checked "$@") || exit $?',
    "",
    "{",
    `${I1}IFS= read -r ubb_verdict`,
    `${I1}while IFS= read -r ubb_line; do`,
    `${I2}printf '%s\\n' "$ubb_line"`,
    `${I1}done`,
    "} <<UBB_REPORT",
    "$ubb_report",
    "UBB_REPORT",
    'exit "$ubb_verdict"',
  ];
  return `${lines.join("\n")}\n`;
}
