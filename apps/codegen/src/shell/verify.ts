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
 * A SUPPLIER'S COST READ OFF THE RESPONSE (#583) is checked by STRUCTURE and
 * never by its size, because a cost of zero is a cost (owner's ruling 5 on
 * #583): its path resolves, what is there is an integer or a decimal string
 * as the response WROTE it, the currency read beside it (where one is)
 * resolves and is one UBB holds, and the amount converts to whole micros
 * exactly. The reading, the pinning and the conversion are the very text the
 * runnable file runs: the same jq program reads the value and says what kind
 * it is, and the same shell functions pin the currency and convert the
 * amount. Which kinds are an amount — a string or an integer — is the
 * runnable file's rule too, restated here as one case pattern so that a
 * failure is reported rather than returned.
 *
 * It is a script that is RUN, not a file that is sourced, so unlike the
 * runnable file it ends with `exit`. Everything it knows of the tenant's
 * declarations is inside its jq programs, in quoted heredocs, and no declared
 * name is ever shell text: the one program that knows the Event Types answers
 * which cost check to run by the check's own name, which the renderer made.
 */
import { COMMENTS, MESSAGES, SHELL_COMMENTS, SHELL_EXIT, SHELL_FILE, SHELL_MESSAGES } from "../catalogue.ts";
import { asComments, statement } from "../comments.ts";
import { FIELD } from "../lifecycle.ts";
import { literalOf } from "../tokens.ts";
import { callTail, readFunctions, readPrograms, reportedCostHelpers, scalarOf } from "./module.ts";
import type { CallPlan, Member, Plan, Value } from "./plan.ts";
import { jqNeedsOf, jqProbe } from "./probe.ts";
import { INDENT, jqLiteral, jqString, shWord } from "./syntax.ts";
import { KIND } from "./written.ts";

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

/** Every record whose supplier's cost is read off the response, with the
 * Event Type it records and the name of the function that checks it. */
function costReads(plan: Plan): { record: CallPlan; eventType: string; check: string }[] {
  return plan.records.flatMap((record) => {
    const eventType = literalOf(record.call, FIELD.eventType);
    const readsACost = record.body.some(
      (field) => field.shape === "scalar" && field.value.kind === "response_cost",
    );
    return typeof eventType === "string" && readsACost
      ? [{ record, eventType, check: `_ubb_check_${callTail(record)}` }]
      : [];
  });
}

/** Which check function each Event Type's cost is checked by, as one jq
 * object: the names are the renderer's, and identifier-safe. */
function declaredCosts(found: ReturnType<typeof costReads>): string[] {
  return [
    ...COMMENTS.verifyCosts.map((line) => `# ${line}`),
    "| {",
    ...found.map(
      ({ eventType, check }, index) =>
        `${I1}${jqString(eventType)}: ${jqString(check)}${index === found.length - 1 ? "" : ","}`,
    ),
    "} as $costs",
  ];
}

/** One line of the report, and a failure counted where the check failed. */
function checkHelper(): string[] {
  return [
    "_ubb_check() {",
    `${I1}if [ "$1" -eq 0 ]; then`,
    `${I2}_ubb_verdict=${shWord(MESSAGES.verifyOk)}`,
    `${I1}else`,
    `${I2}_ubb_verdict=${shWord(MESSAGES.verifyFail)}`,
    `${I2}ubb_failures=$((ubb_failures + 1))`,
    `${I1}fi`,
    `${I1}printf '  %s "%s" %s\\n' "$_ubb_verdict" "$2" "$3"`,
    "}",
  ];
}

/**
 * The checks of one record's cost. The value is read as the runnable file
 * reads it, then checked: there, admissible, and — with the currency pinned
 * as the runnable file pins it — converted exactly. Nothing is checked by
 * size: zero is a cost.
 */
function costCheck(record: CallPlan, check: string): string[] {
  const { field: cost, value } = scalarOf(record, "response_cost")!;
  const currency = scalarOf(record, "response_currency")?.field;
  const reads = readFunctions(record);
  const found = (variable: string) => [
    `${I1}case $_ubb_read in`,
    `${I2}${KIND.missing} | ${KIND.unreadable}) ${variable}=1 ;;`,
    `${I2}*) ${variable}=0 ;;`,
    `${I1}esac`,
  ];
  return [
    `${check}() {`,
    `${I1}_ubb_read=$(${reads.cost} "$1") || _ubb_read=${KIND.unreadable}`,
    ...found("_ubb_found"),
    `${I1}_ubb_check "$_ubb_found" ${cost.name} ${shWord(MESSAGES.verifyResolves)}`,
    `${I1}_ubb_admissible=1`,
    `${I1}if [ "$_ubb_found" -eq 0 ]; then`,
    `${I2}case $_ubb_read in`,
    `${I3}${KIND.string}:* | ${KIND.integer}:*) _ubb_admissible=0; _ubb_amount=\${_ubb_read#*:} ;;`,
    `${I2}esac`,
    `${I2}_ubb_check "$_ubb_admissible" ${cost.name} ${shWord(MESSAGES.verifyAmount)}`,
    `${I1}fi`,
    ...(currency === undefined
      ? [`${I1}_ubb_pin_currency ${shWord(value.declared)} '' 2>/dev/null || return 0`]
      : [
          `${I1}_ubb_read=$(${reads.currency} "$1") || _ubb_read=${KIND.unreadable}`,
          ...found("_ubb_found"),
          `${I1}_ubb_check "$_ubb_found" ${currency.name} ${shWord(MESSAGES.verifyResolves)}`,
          `${I1}[ "$_ubb_found" -eq 0 ] || return 0`,
          `${I1}_ubb_currency_held=1`,
          `${I1}case $_ubb_read in`,
          `${I2}${KIND.string}:*)`,
          `${I3}_ubb_pin_currency '' "\${_ubb_read#*:}" 2>/dev/null && _ubb_currency_held=0`,
          `${I3};;`,
          `${I1}esac`,
          `${I1}_ubb_check "$_ubb_currency_held" ${currency.name} ${shWord(MESSAGES.verifyCurrency)}`,
          `${I1}[ "$_ubb_currency_held" -eq 0 ] || return 0`,
        ]),
    `${I1}[ "$_ubb_admissible" -eq 0 ] || return 0`,
    `${I1}_ubb_converts=1`,
    `${I1}_ubb_to_micros "$_ubb_amount" ${shWord(value.representation)} "$_ubb_currency" 2>/dev/null && _ubb_converts=0`,
    `${I1}_ubb_check "$_ubb_converts" ${cost.name} ${shWord(MESSAGES.verifyConverts)}`,
    "}",
  ];
}

export function renderVerifyScript(plan: Plan): string {
  // A line the program prints, as the jq string that is it.
  const say = jqString;
  const unavailable = SHELL_EXIT.toolUnavailable.status;
  const costs = costReads(plan);
  const program = [
    ...COMMENTS.verifyPaths.map((line) => `# ${line}`),
    ...declaredPaths(plan),
    ...declaredCosts(costs),
    "| def resolve($path):",
    `${I2}reduce $path[] as $segment ({"found": true, "at": .};`,
    `${I3}if .found and (.at | type) == "object" and (.at | has($segment))`,
    `${I3}then {"found": true, "at": .at[$segment]}`,
    `${I3}else {"found": false, "at": null} end);`,
    `${I1}def check($passed; $quantity; $message):`,
    `${I2}"  " + (if $passed then ${say(MESSAGES.verifyOk)} else ${say(MESSAGES.verifyFail)} end)`,
    `${I2}+ " " + ($quantity | tojson) + " " + $message;`,
    `${I1}($declared + $costs) as $known`,
    // The first line says what was done — nothing to check, a usage, or how
    // many checks failed — and the second which cost check runs after these.
    `${I1}| if ($known | length) == 0`,
    `${I1}then "nothing", "-", ${say(MESSAGES.verifyNothing)}`,
    `${I1}elif $given != "2" or ($known | has($event_type) | not)`,
    `${I1}then "usage", "-", ${say(SHELL_MESSAGES.verifyUsage)}, ${say(MESSAGES.verifyEventTypes)},`,
    `${I2}($known | keys_unsorted[] | "  " + tojson)`,
    `${I1}else`,
    `${I2}($declared[$event_type] // {}) as $paths`,
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
    `${I2}| ($failures | tostring), ($costs[$event_type] // "-"), $lines[]`,
    `${I1}end`,
  ];

  const refusal = (message: string) => [
    `${I1}printf '%s\\n' ${shWord(message)} >&2`,
    `${I1}exit ${unavailable}`,
  ];
  // The program answers with what was done, then with the cost check to run
  // after it, then with every line to print. Each line is one line whatever a
  // declared name holds: a name is printed as JSON. It is a function of its
  // own, so that the heredoc is never inside the substitution that captures
  // what it prints.
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
  // What checks a cost: the runnable file's own programs and functions, and
  // one function per record that reads a cost.
  const costing = costs.length === 0
    ? []
    : [
        ...asComments(SHELL_COMMENTS.verifyCosts),
        `${SHELL_EXIT.valueRefused.name}=${SHELL_EXIT.valueRefused.status}`,
        "",
        ...costs.flatMap(({ record }) => readPrograms(record)),
        ...reportedCostHelpers(false),
        "",
        ...checkHelper(),
        ...costs.flatMap(({ record, check }) => ["", ...costCheck(record, check)]),
        "",
      ];
  const programs = [...checked, ...costing].join("\n");
  const lines = [
    ...asComments(SHELL_COMMENTS.verify),
    ...asComments([statement("configuration_fingerprint", plan.header.configuration_fingerprint ?? null)]),
    "",
    ...asComments(SHELL_COMMENTS.verifyPreflight),
    "command -v jq >/dev/null 2>&1 || {",
    ...refusal(SHELL_MESSAGES.jqMissing),
    "}",
    "ubb_probe=0",
    // For exactly what the programs below ask of jq.
    ...jqProbe("", "ubb_probe", jqNeedsOf(programs)),
    `[ "$ubb_probe" -eq 0 ] || {`,
    ...refusal(SHELL_MESSAGES.jqUnusable),
    "}",
    "",
    ...checked,
    "",
    ...costing,
    'ubb_report=$(ubb_checked "$@") || exit $?',
    "",
    "{",
    `${I1}IFS= read -r ubb_verdict`,
    `${I1}IFS= read -r ubb_then`,
    `${I1}while IFS= read -r ubb_line; do`,
    `${I2}printf '%s\\n' "$ubb_line"`,
    `${I1}done`,
    "} <<UBB_REPORT",
    "$ubb_report",
    "UBB_REPORT",
    "case $ubb_verdict in",
    `${I1}nothing) exit 0 ;;`,
    `${I1}usage) exit 2 ;;`,
    "esac",
    "ubb_failures=$ubb_verdict",
    ...(costs.length === 0 ? [] : ['[ "$ubb_then" = - ] || "$ubb_then" "$2"']),
    'if [ "$ubb_failures" -gt 0 ]; then',
    `${I1}printf '%s %s\\n' "$ubb_failures" ${shWord(MESSAGES.verifyFailed)}`,
    `${I1}exit 1`,
    "fi",
    `printf '%s\\n' ${shWord(MESSAGES.verifyPassed)}`,
    "exit 0",
  ];
  return `${lines.join("\n")}\n`;
}
