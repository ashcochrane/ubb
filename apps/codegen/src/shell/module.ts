/**
 * The runnable file: the one file a tenant sources and never edits.
 *
 * Everything a tenant's running code needs of what the Blueprint resolved is
 * in here — every literal, every declared path, every fact stated beside the
 * value it is about — and none of it is in a call-site block. It is POSIX
 * shell, written to be SOURCED into a script UBB never sees: it sets no shell
 * option, never calls `exit`, and holds no variable that is not spelled
 * `UBB_…` or `_ubb_…`.
 *
 * THE THREE CLASSES ARE SHAPES. A `platform_known` token is written as a
 * literal. A `runtime_bound` token is a `name=value` argument of the function
 * for its call, named exactly as the Blueprint names it; left out or passed
 * empty, the function refuses before anything is sent. A `secret_reference`
 * is `$UBB_API_KEY`, read from the environment and handed to curl on standard
 * input. A literal with no configured value keeps its place and is written as
 * a call that raises.
 *
 * EVERY JQ PROGRAM ARRIVES THROUGH A QUOTED HEREDOC, read by jq from standard
 * input (`--from-file /dev/stdin`). The shell expands nothing inside one, so
 * no declared name can end a string or start a command. Runtime values reach
 * a program only as `--arg`, `--argjson` or `--slurpfile` — or, where a
 * supplier's cost is read off the response as it was written (#583), as the
 * response file the program reads as text, its one input. Every line of a
 * program is indented, and the delimiter is not: no line generated from a
 * declaration can be the line that ends the heredoc.
 *
 * AND EVERY PROGRAM IS A FUNCTION OF ITS OWN, WHICH IS NOTHING ELSE
 * (`_ubb_jq_…`). A heredoc is never opened inside `$( )`: bash 3.2, which is
 * what macOS ships, reads the text of a heredoc there as shell, and one
 * backtick in a declared name ends the file. What is captured is the
 * function's output, so the heredoc itself sits where every shell reads it
 * as text.
 *
 * THE STOP IS A STATUS, AND IT IS NEVER PRODUCED IN A SUBSHELL. A record that
 * is answered with a stop leaves the stop's metadata in a variable and
 * returns the reserved status. Every function on that path is called as a
 * plain command. The only things this file ever runs inside `$( )` are a
 * program function, which sets nothing and returns jq's status, and the
 * credential piped to curl — so what a function set is still there for its
 * caller, and its status is the one the caller sees. Nothing here is
 * `set -e`'s to propagate: every status is tested where it is produced.
 */
import {
  AMOUNT_REPRESENTATION,
  COMMENTS,
  ENVIRONMENT,
  MESSAGES,
  MICROS_PER_MINOR_UNIT,
  PRICING_MODE_COMMENTS,
  SHELL,
  SHELL_COMMENTS,
  SHELL_EXIT,
  SHELL_FILE,
  SHELL_MESSAGES,
  SHELL_READINESS_COMMENTS,
} from "../catalogue.ts";
import { asComments } from "../comments.ts";
import { headerText } from "../header.ts";
import { FACT, FIELD } from "../lifecycle.ts";
import { refuse } from "../blueprint.ts";
import { factOfField, said, SAID_OF } from "../tokens.ts";
import {
  routeWith,
  type BodyField,
  type CallPlan,
  type Member,
  type Parameter,
  type Plan,
  type Value,
} from "./plan.ts";
import { jqNeedsOf, jqProbe, type JqNeeds } from "./probe.ts";
import {
  INDENT,
  jqLiteral,
  jqString,
  jqVariable,
  shVariable,
  shWord,
  wireName,
} from "./syntax.ts";
import { readHelpers, writtenProgram } from "./written.ts";

const I1 = INDENT;
const I2 = INDENT.repeat(2);
const I3 = INDENT.repeat(3);
const I4 = INDENT.repeat(4);

const STOP = `"$${SHELL.stopExitStatusName}"`;

/** A named status, as the word a `return` is given. */
function status(of: { readonly name: string }): string {
  return `"$${of.name}"`;
}

/** What the file turned out to need, found while writing its calls. */
interface Uses {
  notReady: boolean;
  reportedCost: boolean;
  /** A cost the caller passes, which the comments speak to (#578). */
  callerCost: boolean;
  /** A supplier's cost read off the response (#583). */
  responseRead: boolean;
  /** A currency read off the response, which needs a helper of its own. */
  currencyRead: boolean;
  wholeNumber: boolean;
  urlValue: boolean;
}

// ---------------------------------------------------------------------------
// jq programs
// ---------------------------------------------------------------------------

/** The jq functions a program may call, each defined in the program itself. */
const JQ = {
  read: "read",
  notConfigured: "not_configured",
  notRenderable: "not_renderable",
} as const;

function jqDefinitions(needs: ReadonlySet<string>): string[] {
  const lines: string[] = [];
  if (needs.has(JQ.notConfigured)) {
    lines.push(
      `def ${JQ.notConfigured}($name):`,
      `${I1}error($name + ${jqString(` ${SAID_OF.unconfigured}.`)});`,
    );
  }
  if (needs.has(JQ.notRenderable)) {
    lines.push(
      `def ${JQ.notRenderable}($name):`,
      `${I1}error($name + ${jqString(` ${SAID_OF.not_renderable}.`)});`,
    );
  }
  if (needs.has(JQ.read)) {
    const most = "9".repeat(SHELL_FILE.exactDigits);
    lines.push(
      `def ${JQ.read}($path):`,
      `${I1}getpath($path) as $value`,
      `${I1}| if $value == null`,
      `${I1}  then error(${jqString(`${SHELL_MESSAGES.noValue} `)} + ($path | tojson))`,
      `${I1}  elif ($value | type) != "number" or $value != ($value | floor)`,
      `${I1}  then error(${jqString(`${SHELL_MESSAGES.notWhole} `)} + ($path | tojson))`,
      `${I1}  elif $value > ${most} or $value < -${most}`,
      `${I1}  then error(${jqString(`${SHELL_MESSAGES.inexact} `)} + ($path | tojson))`,
      `${I1}  else $value end;`,
    );
  }
  return lines;
}

/** A value as the jq expression that evaluates to it, or `null` where the
 * shell writes it into the body itself. */
function jqValue(value: Value, needs: Set<string>): string | null {
  switch (value.kind) {
    case "literal":
      return jqLiteral(value.value);
    case "parameter":
      return `$${jqVariable(value.parameter.name)}`;
    case "read":
      needs.add(JQ.read);
      return `($${jqVariable(value.parameter.name)}[0] | ${JQ.read}(${jqLiteral(value.path)}))`;
    case "unconfigured":
      needs.add(JQ.notConfigured);
      return `${JQ.notConfigured}(${jqString(value.token)})`;
    case "not_renderable":
      needs.add(JQ.notRenderable);
      return `${JQ.notRenderable}(${jqString(value.token)})`;
    case "cost":
    case "response_cost":
    case "response_currency":
      return null;
  }
}

interface Line {
  readonly comments: readonly string[];
  /** `null` for a key that is stated and not sent. */
  readonly text: string | null;
}

/** Lines as the members of one jq object: a comma after every member but the
 * last, and a member that is only stated still stated. */
function members(lines: readonly Line[], indent: string): string[] {
  const last = lines.map((line) => line.text !== null).lastIndexOf(true);
  return lines.flatMap((line, index) => [
    ...line.comments.map((comment) => `${indent}# ${comment}`),
    ...(line.text === null ? [] : [`${indent}${line.text}${index === last ? "" : ","}`]),
  ]);
}

function memberLine(member: Member, needs: Set<string>): Line {
  const value = member.value === null ? null : jqValue(member.value, needs);
  return {
    comments: member.comments,
    text: value === null ? null : `${jqString(member.key)}: ${value}`,
  };
}

/** The object a call sends, as a jq program. A field the shell writes into
 * the body itself is stated and left out; one that is sent only where it was
 * given is added after the object. */
function bodyProgram(call: CallPlan): string[] {
  const needs = new Set<string>();
  const always = call.body.filter((field) => !givenOnly(field));
  const lines: string[] = [];
  const last = always.map(sent).lastIndexOf(true);
  always.forEach((field, index) => {
    // A converted cost is stated where it is converted, in the shell.
    if (!sent(field)) return;
    const comma = index === last ? "" : ",";
    if (field.shape === "keyed") {
      const inner = members(
        field.members.map((member) => memberLine(member, needs)),
        I2,
      );
      lines.push(`${I1}${jqString(field.name)}: {`, ...inner, `${I1}}${comma}`);
      return;
    }
    lines.push(
      ...field.comments.map((comment) => `${I1}# ${comment}`),
      `${I1}${jqString(field.name)}: ${jqValue(field.value, needs)}${comma}`,
    );
  });
  const whereGiven = call.body.flatMap((field) => {
    if (field.shape !== "scalar" || !field.optional || field.value.kind !== "parameter") return [];
    const variable = `$${jqVariable(field.value.parameter.name)}`;
    return [`+ (if ${variable} == "" then {} else {${jqString(field.name)}: ${variable}} end)`];
  });
  return [...jqDefinitions(needs), "{", ...lines, "}", ...whereGiven];
}

/** Whether a field is sent only where its parameter was given. */
function givenOnly(field: BodyField): boolean {
  return field.shape === "scalar" && field.optional;
}

/** Values the shell writes into the body itself, and jq never: a converted
 * cost, and a currency read off the response once it is pinned. */
const WRITTEN_BY_THE_SHELL: readonly Value["kind"][] = ["cost", "response_cost", "response_currency"];

/** Whether jq writes a field: every one but those the shell writes. */
function sent(field: BodyField): boolean {
  return field.shape === "keyed" || !WRITTEN_BY_THE_SHELL.includes(field.value.kind);
}

/** The function that is the jq program of `name`, and nothing else. */
function programName(name: string): string {
  return `_ubb_jq_${name}`;
}

/**
 * One jq program, as a function that runs it: jq, what it is handed, and the
 * program in a quoted heredoc on its standard input. Every line of the
 * program is indented and the delimiter is not, so no line of a program can
 * be the line that ends it. The function holds no other command: it sets
 * nothing, and what it returns is jq's own status. A program that reads a
 * file as its input names it last, after the program.
 */
function program(
  name: string,
  flags: readonly string[],
  bindings: readonly string[],
  lines: readonly string[],
  input: string | null = null,
): string[] {
  if (lines.some((line) => line.trim() === "")) refuse("a jq program holds a blank line");
  return [
    `${programName(name)}() {`,
    `${I1}jq ${flags.join(" ")} \\`,
    ...bindings.map((binding) => `${I2}${binding} \\`),
    `${I2}--from-file /dev/stdin${input === null ? "" : ` ${input}`} <<'${SHELL_FILE.heredoc}'`,
    ...lines.map((line) => `${I1}${line}`),
    SHELL_FILE.heredoc,
    "}",
  ];
}

/** `variable=$(<the program of name>)`, and what to do where jq fails. */
function capture(
  variable: string,
  name: string,
  given: readonly string[],
  onFailure: readonly string[],
): string[] {
  const [first, ...rest] = onFailure;
  const call = [programName(name), ...given].join(" ");
  return [`${I1}${variable}=$(${call}) || ${first!}`, ...rest];
}

function binding(parameter: Parameter): string | null {
  const from = `"$${shVariable(parameter.name)}"`;
  switch (parameter.use) {
    case "text":
      return `--arg ${jqVariable(parameter.name)} ${from}`;
    case "number":
      return `--argjson ${jqVariable(parameter.name)} ${from}`;
    case "file":
      return `--slurpfile ${jqVariable(parameter.name)} ${from}`;
    case "cost":
    case "place":
    case "unread":
      return null;
  }
}

// ---------------------------------------------------------------------------
// The file's own helpers
// ---------------------------------------------------------------------------

function say(message: string): string {
  return `printf '%s\\n' ${shWord(message)} >&2`;
}

function constants(): string[] {
  return [
    ...asComments(SHELL_COMMENTS.statuses),
    `${SHELL.stopExitStatusName}=${SHELL.stopExitStatus}`,
    ...Object.values(SHELL_EXIT).map((exit) => `${exit.name}=${exit.status}`),
    "",
    ...asComments(SHELL_COMMENTS.outputs),
    `${SHELL_FILE.taskId}=`,
    `${SHELL_FILE.response}=`,
    `${SHELL_FILE.stopRequested}=`,
    "",
    "_ubb_ready=",
    "_ubb_closed=",
    "_ubb_stop_met=",
  ];
}

/** Preflight, probing for exactly what `needs` says this file's programs
 * ask of jq. */
function preflight(needs: JqNeeds): string[] {
  const unavailable = status(SHELL_EXIT.toolUnavailable);
  return [
    ...asComments(SHELL_COMMENTS.preflight),
    "_ubb_preflight() {",
    `${I1}[ -z "$_ubb_ready" ] || return 0`,
    `${I1}command -v jq >/dev/null 2>&1 || {`,
    `${I2}${say(SHELL_MESSAGES.jqMissing)}`,
    `${I2}return ${unavailable}`,
    `${I1}}`,
    `${I1}_ubb_probe=0`,
    ...jqProbe(I1, "_ubb_probe", needs),
    `${I1}[ "$_ubb_probe" -eq 0 ] || {`,
    `${I2}${say(SHELL_MESSAGES.jqUnusable)}`,
    `${I2}return ${unavailable}`,
    `${I1}}`,
    `${I1}command -v curl >/dev/null 2>&1 || {`,
    `${I2}${say(SHELL_MESSAGES.curlMissing)}`,
    `${I2}return ${unavailable}`,
    `${I1}}`,
    `${I1}curl --fail-with-body --version >/dev/null 2>&1 || {`,
    `${I2}${say(SHELL_MESSAGES.curlUnusable)}`,
    `${I2}return ${unavailable}`,
    `${I1}}`,
    `${I1}_ubb_ready=1`,
    "}",
  ];
}

function environment(plan: Plan): string[] {
  const refusal = (variable: string) => [
    `${I1}[ -n "\${${variable}:-}" ] || {`,
    `${I2}${say(`${variable} ${MESSAGES.environmentNotSet}`)}`,
    `${I2}return ${status(SHELL_EXIT.notConfigured)}`,
    `${I1}}`,
  ];
  return [
    ...asComments(SHELL_COMMENTS.environment),
    "_ubb_environment() {",
    // Where the API is, is read and never defaulted: an unset or an empty
    // variable refuses here, before anything is sent.
    ...asComments(COMMENTS.baseUrl, I1),
    ...refusal(ENVIRONMENT.baseUrl),
    ...asComments(COMMENTS.apiKey, I1),
    ...refusal(plan.credential.binding.environmentVariable),
    "}",
  ];
}

function request(plan: Plan): string[] {
  const credential = plan.credential.binding.environmentVariable;
  return [
    ...asComments(SHELL_COMMENTS.request),
    "_ubb_post() {",
    `${I1}_ubb_sent=0`,
    `${I1}${SHELL_FILE.response}=$(printf 'Authorization: Bearer %s\\n' "$${credential}" | curl \\`,
    `${I2}--silent --show-error --fail-with-body \\`,
    `${I2}--request POST \\`,
    `${I2}--header @- \\`,
    `${I2}--header 'Content-Type: application/json' \\`,
    `${I2}--data-binary "$2" \\`,
    `${I2}"\${${ENVIRONMENT.baseUrl}%/}$1"`,
    `${I1}) || _ubb_sent=$?`,
    `${I1}[ "$_ubb_sent" -ne 0 ] || return 0`,
    `${I1}[ -z "$${SHELL_FILE.response}" ] || printf '%s\\n' "$${SHELL_FILE.response}" >&2`,
    // Whatever a request fails with, it is never the status a stop has.
    `${I1}[ "$_ubb_sent" -ne ${STOP} ] || _ubb_sent=1`,
    `${I1}return "$_ubb_sent"`,
    "}",
  ];
}

function unreadable(): string[] {
  return [
    "{",
    `${I2}${say(SHELL_MESSAGES.responseUnreadable)}`,
    `${I2}return ${status(SHELL_EXIT.responseUnreadable)}`,
    `${I1}}`,
  ];
}

function started(): string[] {
  return [
    ...asComments(SHELL_COMMENTS.startedTask),
    ...program(
      "task_id",
      ["--raw-output", "--null-input"],
      [`--arg response "$${SHELL_FILE.response}"`],
      [
        "($response | fromjson) as $started",
        `| if ($started | type) != "object" or ($started.task_id | type) != "string"`,
        `${I1}   or $started.task_id == ""`,
        `${I1}then error(${jqString(SHELL_MESSAGES.noTaskId)})`,
        `${I1}else $started.task_id end`,
      ],
    ),
    "",
    "_ubb_started() {",
    ...capture(SHELL_FILE.taskId, "task_id", [], unreadable()),
    "}",
  ];
}

/**
 * Reading an acknowledgement. The stop's metadata carries the four fields the
 * acknowledgement and the request publish today, by their own names; what is
 * logged is exactly this, and nothing is worked out from it.
 */
function acknowledgement(): string[] {
  return [
    ...asComments(SHELL_COMMENTS.acknowledgement),
    ...program(
      "stop",
      ["--raw-output", "--null-input"],
      [`--arg response "$${SHELL_FILE.response}"`, `--arg idempotency_key "$1"`],
      [
        "($response | fromjson) as $acknowledgement",
        `| if ($acknowledgement | type) != "object"`,
        `${I1}   or ($acknowledgement.event_id | type) != "string"`,
        `${I1}then error(${jqString(SHELL_MESSAGES.noEventId)})`,
        `${I1}elif $acknowledgement.stop == true`,
        `${I1}then {`,
        `${I2}"event_id": $acknowledgement.event_id,`,
        `${I2}"idempotency_key": $idempotency_key,`,
        `${I2}"stop_scope": $acknowledgement.stop_scope,`,
        `${I2}"stop_reason": $acknowledgement.stop_reason`,
        `${I1}} | tojson`,
        `${I1}else "null" end`,
      ],
    ),
    "",
    "_ubb_acknowledge() {",
    // Read in a subshell, and acted on here: the variable is set and the
    // status returned by this function, which is called as a plain command.
    ...capture("_ubb_stop", "stop", ['"$1"'], unreadable()),
    `${I1}[ "$_ubb_stop" != null ] || return 0`,
    `${I1}${SHELL_FILE.stopRequested}=$_ubb_stop`,
    // Kept for the boundary too, which a later call's result cannot clear.
    `${I1}_ubb_stop_met=$_ubb_stop`,
    `${I1}return ${STOP}`,
    "}",
  ];
}

function parameterHelpers(uses: Uses): string[] {
  const refused = status(SHELL_EXIT.valueRefused);
  const lines = [
    ...asComments(SHELL_COMMENTS.parameters),
    "_ubb_missing() {",
    `${I1}printf '%s: %s %s\\n' "$1" "$2" ${shWord(SHELL_MESSAGES.missing)} >&2`,
    "}",
    "",
    "_ubb_unknown() {",
    `${I1}printf '%s: %s %s\\n' "$1" "\${2%%=*}" ${shWord(SHELL_MESSAGES.unknown)} >&2`,
    "}",
  ];
  if (uses.wholeNumber) {
    const tooLong = "?".repeat(SHELL_FILE.exactDigits + 1);
    lines.push(
      "",
      ...asComments(SHELL_COMMENTS.wholeNumber),
      "_ubb_whole_number() {",
      `${I1}case \${3#-} in`,
      `${I2}'' | *[!0-9]* | 0?* | ${tooLong}*)`,
      `${I3}printf '%s: %s %s\\n' "$1" "$2" ${shWord(SHELL_MESSAGES.wholeNumber)} >&2`,
      `${I3}return ${refused}`,
      `${I3};;`,
      `${I1}esac`,
      "}",
    );
  }
  if (uses.urlValue) {
    lines.push(
      "",
      ...asComments(SHELL_COMMENTS.urlValue),
      "_ubb_url_value() {",
      `${I1}case $3 in`,
      `${I2}. | .. | *[!A-Za-z0-9._~-]*)`,
      `${I3}printf '%s: %s %s\\n' "$1" "$2" ${shWord(SHELL_MESSAGES.urlValue)} >&2`,
      `${I3}return ${refused}`,
      `${I3};;`,
      `${I1}esac`,
      "}",
    );
  }
  return lines;
}

function notReadyHelper(): string[] {
  return [
    ...asComments(SHELL_COMMENTS.notReady),
    "_ubb_not_ready() {",
    `${I1}printf '%s (%s) %s' "$1" "$2" ${shWord(MESSAGES.notReady)} >&2`,
    `${I1}shift 2`,
    `${I1}for _ubb_reason in "$@"; do`,
    `${I2}printf ' %s' "$_ubb_reason" >&2`,
    `${I1}done`,
    `${I1}printf '\\n' >&2`,
    "}",
  ];
}

/** How many places to move the point for a multiplier that is a power of ten,
 * which every currency's is. */
function shift(micros: number): number {
  const places = String(micros).length - 1;
  if (micros !== 10 ** places) {
    return refuse(`${micros} micros in a minor unit is not a power of ten`);
  }
  return places;
}

/** A currency code as a pattern that matches it in either case. */
function eitherCase(code: string): string {
  return Array.from(code, (letter) => `[${letter.toUpperCase()}${letter.toLowerCase()}]`).join("");
}

export function reportedCostHelpers(callerCost: boolean): string[] {
  const refused = status(SHELL_EXIT.valueRefused);
  const refuseAmount = (message: string, indent: string) => [
    `${indent}printf '%s %s\\n' "$1" ${shWord(message)} >&2`,
    `${indent}return ${refused}`,
  ];
  const limit = SHELL_FILE.microsLimit;
  const currencies = Object.entries(MICROS_PER_MINOR_UNIT)
    .sort()
    .map(
      ([code, micros]) =>
        `${I2}${eitherCase(code)}) _ubb_currency=${code}; _ubb_shift=${shift(micros)} ;;`,
    );
  const { micros, minorUnits: minor, majorUnitsDecimal: major } = AMOUNT_REPRESENTATION;
  const stripZeros = (variable: string, indent: string) => [
    `${indent}while :; do`,
    `${indent}${I1}case $${variable} in`,
    `${indent}${I2}0?*) ${variable}=\${${variable}#0} ;;`,
    `${indent}${I2}*) break ;;`,
    `${indent}${I1}esac`,
    `${indent}done`,
  ];
  return [
    ...asComments([...SHELL_COMMENTS.reportedCost, ...(callerCost ? SHELL_COMMENTS.callerCost : [])]),
    "_ubb_known_currency() {",
    `${I1}case $1 in`,
    ...currencies,
    `${I2}*)`,
    `${I3}printf '%s %s\\n' "$1" ${shWord(MESSAGES.currencyUnknown)} >&2`,
    `${I3}return ${refused}`,
    `${I3};;`,
    `${I1}esac`,
    "}",
    "",
    "_ubb_trim() {",
    `${I1}_ubb_trimmed=\${1#"\${1%%[![:space:]]*}"}`,
    `${I1}_ubb_trimmed=\${_ubb_trimmed%"\${_ubb_trimmed##*[![:space:]]}"}`,
    "}",
    "",
    "_ubb_pin_currency() {",
    `${I1}_ubb_trim "$1"`,
    `${I1}_ubb_pinned=$_ubb_trimmed`,
    `${I1}_ubb_trim "$2"`,
    `${I1}_ubb_supplied=$_ubb_trimmed`,
    `${I1}if [ -z "$_ubb_pinned" ] && [ -z "$_ubb_supplied" ]; then`,
    `${I2}${say(MESSAGES.currencyNone)}`,
    `${I2}return ${refused}`,
    `${I1}fi`,
    `${I1}if [ -n "$_ubb_pinned" ]; then`,
    `${I2}_ubb_known_currency "$_ubb_pinned" || return $?`,
    `${I2}_ubb_pinned=$_ubb_currency`,
    `${I1}fi`,
    `${I1}if [ -n "$_ubb_supplied" ]; then`,
    `${I2}_ubb_known_currency "$_ubb_supplied" || return $?`,
    `${I2}_ubb_supplied=$_ubb_currency`,
    `${I1}fi`,
    `${I1}if [ -n "$_ubb_pinned" ] && [ -n "$_ubb_supplied" ] && [ "$_ubb_pinned" != "$_ubb_supplied" ]; then`,
    `${I2}printf '%s: %s, %s\\n' ${shWord(MESSAGES.currencyDisagrees)} "$_ubb_supplied" "$_ubb_pinned" >&2`,
    `${I2}return ${refused}`,
    `${I1}fi`,
    `${I1}_ubb_currency=\${_ubb_pinned:-$_ubb_supplied}`,
    "}",
    "",
    "_ubb_to_micros() {",
    `${I1}case $2 in`,
    `${I2}${micros}) _ubb_shift=0 ;;`,
    `${I2}${minor}) _ubb_known_currency "$3" || return $? ;;`,
    `${I2}${major}) _ubb_shift=6 ;;`,
    `${I2}*)`,
    `${I3}printf '%s %s\\n' "$2" ${shWord(MESSAGES.representation)} >&2`,
    `${I3}return ${refused}`,
    `${I3};;`,
    `${I1}esac`,
    `${I1}_ubb_trim "$1"`,
    `${I1}_ubb_text=$_ubb_trimmed`,
    `${I1}while :; do`,
    `${I2}case $_ubb_text in`,
    `${I3}*_*) _ubb_text=\${_ubb_text%%_*}\${_ubb_text#*_} ;;`,
    `${I3}*) break ;;`,
    `${I2}esac`,
    `${I1}done`,
    `${I1}_ubb_sign=`,
    `${I1}case $_ubb_text in`,
    `${I2}-*) _ubb_sign=-; _ubb_text=\${_ubb_text#-} ;;`,
    `${I2}+*) _ubb_text=\${_ubb_text#+} ;;`,
    `${I1}esac`,
    `${I1}_ubb_exponent=0`,
    `${I1}_ubb_exponent_sign=`,
    `${I1}case $_ubb_text in`,
    `${I2}*[eE]*)`,
    `${I3}_ubb_exponent=\${_ubb_text#*[eE]}`,
    `${I3}_ubb_text=\${_ubb_text%%[eE]*}`,
    `${I3}case $_ubb_exponent in`,
    `${I4}-*) _ubb_exponent_sign=-; _ubb_exponent=\${_ubb_exponent#-} ;;`,
    `${I4}+*) _ubb_exponent=\${_ubb_exponent#+} ;;`,
    `${I3}esac`,
    `${I3};;`,
    `${I1}esac`,
    `${I1}case $_ubb_text in`,
    `${I2}*.*) _ubb_whole=\${_ubb_text%%.*}; _ubb_fraction=\${_ubb_text#*.} ;;`,
    `${I2}*) _ubb_whole=$_ubb_text; _ubb_fraction= ;;`,
    `${I1}esac`,
    `${I1}_ubb_digits=$_ubb_whole$_ubb_fraction`,
    `${I1}case $_ubb_digits in`,
    `${I2}'' | *[!0-9]*)`,
    ...refuseAmount(MESSAGES.notANumber, I3),
    `${I3};;`,
    `${I1}esac`,
    `${I1}case $_ubb_exponent in`,
    `${I2}'' | *[!0-9]*)`,
    ...refuseAmount(MESSAGES.notANumber, I3),
    `${I3};;`,
    `${I1}esac`,
    ...stripZeros("_ubb_digits", I1),
    ...stripZeros("_ubb_exponent", I1),
    // An exponent of seven digits or more is past the bound whatever the
    // digits are, and is refused before any arithmetic is done on it.
    `${I1}case $_ubb_exponent in`,
    `${I2}???????*)`,
    ...refuseAmount(MESSAGES.exponent, I3),
    `${I3};;`,
    `${I1}esac`,
    `${I1}_ubb_scale=$((\${_ubb_exponent_sign}\${_ubb_exponent} - \${#_ubb_fraction}))`,
    `${I1}while [ "$_ubb_scale" -lt 0 ]; do`,
    `${I2}case $_ubb_digits in`,
    `${I3}?*0) _ubb_digits=\${_ubb_digits%0}; _ubb_scale=$((_ubb_scale + 1)) ;;`,
    `${I3}*) break ;;`,
    `${I2}esac`,
    `${I1}done`,
    `${I1}if [ "$_ubb_scale" -gt ${SHELL_FILE.exponentLimit} ] || [ "$_ubb_scale" -lt -${SHELL_FILE.exponentLimit} ]; then`,
    ...refuseAmount(MESSAGES.exponent, I2),
    `${I1}fi`,
    `${I1}_ubb_scale=$((_ubb_scale + _ubb_shift))`,
    `${I1}if [ "$_ubb_scale" -lt 0 ] && [ "$_ubb_digits" != 0 ]; then`,
    ...refuseAmount(MESSAGES.fractional, I2),
    `${I1}fi`,
    `${I1}while [ "$_ubb_scale" -gt 0 ] && [ "$_ubb_digits" != 0 ]; do`,
    `${I2}_ubb_digits=\${_ubb_digits}0`,
    `${I2}_ubb_scale=$((_ubb_scale - 1))`,
    `${I1}done`,
    // The largest amount a money column holds, compared digit group by digit
    // group: the whole figure is more than shell arithmetic is promised.
    `${I1}case $_ubb_digits in`,
    `${I2}${"?".repeat(limit.length + 1)}*)`,
    ...refuseAmount(MESSAGES.tooLarge, I3),
    `${I3};;`,
    `${I2}${"?".repeat(limit.length)})`,
    `${I3}_ubb_low=\${_ubb_digits#${"?".repeat(10)}}`,
    `${I3}_ubb_middle=\${_ubb_digits#?}`,
    `${I3}_ubb_middle=\${_ubb_middle%${"?".repeat(9)}}`,
    `${I3}_ubb_high=\${_ubb_digits%${"?".repeat(18)}}`,
    `${I3}if [ "$_ubb_high" -gt ${limit.slice(0, 1)} ] ||`,
    `${I4}{ [ "$_ubb_high" -eq ${limit.slice(0, 1)} ] && [ "$_ubb_middle" -gt ${limit.slice(1, 10)} ]; } ||`,
    `${I4}{ [ "$_ubb_high" -eq ${limit.slice(0, 1)} ] && [ "$_ubb_middle" -eq ${limit.slice(1, 10)} ] && [ "$_ubb_low" -gt ${limit.slice(10)} ]; }; then`,
    ...refuseAmount(MESSAGES.tooLarge, I4),
    `${I3}fi`,
    `${I3};;`,
    `${I1}esac`,
    `${I1}[ "$_ubb_digits" != 0 ] || _ubb_sign=`,
    `${I1}_ubb_micros=$_ubb_sign$_ubb_digits`,
    "}",
  ];
}

// ---------------------------------------------------------------------------
// A call
// ---------------------------------------------------------------------------

/** Each value this file writes as a call that raises, as the sentence that
 * says why. A value the plan wrote as unconfigured is said to have no
 * configured value — nothing configures it, or (as since #578) it is read
 * off a response this target cannot read, which the header's diagnostic
 * names. One the tenant declared and this Code Builder version cannot yet
 * generate (#571) is said to be exactly that. The sentence is made here, so
 * the helper that prints it states no reason of its own. */
function unwritten(call: CallPlan): string[] {
  const sentence = (value: Value | null): string[] =>
    value?.kind === "unconfigured" || value?.kind === "not_renderable"
      ? [said({ name: value.token, why: value.kind })]
      : [];
  return call.body.flatMap((field) =>
    field.shape === "keyed"
      ? field.members.flatMap((member) => sentence(member.value))
      : sentence(field.value),
  );
}

function guard(uses: Uses, call: CallPlan): string[] {
  // By the server's verdict, and by this target's own: a value it has no way
  // to write is a call it does not send, whatever the verdict says.
  const reasons = unwritten(call);
  if (call.call.readiness === "complete" && reasons.length === 0) return [];
  uses.notReady = true;
  const saying = reasons
    .map((reason) => ` ${shWord(reason)}`)
    .join("");
  return [
    ...asComments(COMMENTS.notReadyCall, I1),
    `${I1}_ubb_not_ready ${shWord(call.call.operationId)} ${shWord(call.call.readiness)}${saying}`,
    `${I1}return ${status(SHELL_EXIT.notConfigured)}`,
  ];
}

/** Reading `name=value` arguments into the function's own variables, and
 * refusing one that is left out, passed empty, or not the call's. */
function readArguments(call: CallPlan): string[] {
  const usage = status(SHELL_EXIT.usage);
  return [
    ...call.parameters.map((parameter) => `${I1}${shVariable(parameter.name)}=`),
    `${I1}for _ubb_argument in "$@"; do`,
    `${I2}case $_ubb_argument in`,
    ...call.parameters.map(
      (parameter) =>
        `${I3}${parameter.name}=*) ${shVariable(parameter.name)}=\${_ubb_argument#${parameter.name}=} ;;`,
    ),
    `${I3}*)`,
    `${I4}_ubb_unknown ${call.name} "$_ubb_argument"`,
    `${I4}return ${usage}`,
    `${I4};;`,
    `${I2}esac`,
    `${I1}done`,
    ...call.parameters
      .filter((parameter) => parameter.required)
      .flatMap((parameter) => [
        `${I1}[ -n "$${shVariable(parameter.name)}" ] || {`,
        `${I2}_ubb_missing ${call.name} ${parameter.name}`,
        `${I2}return ${usage}`,
        `${I1}}`,
      ]),
  ];
}

function checks(uses: Uses, call: CallPlan): string[] {
  return call.parameters.flatMap((parameter) => {
    const value = `"$${shVariable(parameter.name)}"`;
    if (parameter.use === "number") {
      uses.wholeNumber = true;
      return [`${I1}_ubb_whole_number ${call.name} ${parameter.name} ${value} || return $?`];
    }
    if (parameter.use === "place") {
      uses.urlValue = true;
      return [`${I1}_ubb_url_value ${call.name} ${parameter.name} ${value} || return $?`];
    }
    return [];
  });
}

/** The fields the shell converts and writes into the body itself. */
function costs(call: CallPlan): { field: Cost; value: Extract<Value, { kind: "cost" }> }[] {
  return call.body.flatMap((field) =>
    field.shape === "scalar" && field.value.kind === "cost" ? [{ field, value: field.value }] : [],
  );
}

type Cost = Extract<BodyField, { shape: "scalar" }>;

/** A call's name without the file's prefix: what the functions written for
 * it — its programs, and a verify script's check — are named by. */
export function callTail(call: CallPlan): string {
  return call.name.replace(/^ubb_/, "");
}

/** The scalar field of `call` whose value is of `kind`, or `undefined`. */
export function scalarOf<K extends Value["kind"]>(
  call: CallPlan,
  kind: K,
): { field: Cost; value: Extract<Value, { kind: K }> } | undefined {
  for (const field of call.body) {
    if (field.shape === "scalar" && field.value.kind === kind) {
      return { field, value: field.value as Extract<Value, { kind: K }> };
    }
  }
  return undefined;
}

/** The two programs a call reads its cost, and the currency beside it, off
 * the response with. */
function readProgramNames(call: CallPlan): { cost: string; currency: string } {
  const tail = callTail(call);
  return { cost: `cost_${tail}`, currency: `currency_${tail}` };
}

/** The same two programs by the names of the functions they are written as,
 * which the verify script calls. */
export function readFunctions(call: CallPlan): { cost: string; currency: string } {
  const names = readProgramNames(call);
  return { cost: programName(names.cost), currency: programName(names.currency) };
}

/** Each program that reads a value off `call`'s response as written. */
export function readPrograms(call: CallPlan): string[] {
  const cost = scalarOf(call, "response_cost");
  const currency = scalarOf(call, "response_currency");
  if (cost === undefined) {
    return currency === undefined
      ? []
      : refuse(`the call ${call.name} reads a currency off the response with no cost beside it`);
  }
  const names = readProgramNames(call);
  const reading = (name: string, path: readonly string[]) =>
    program(name, ["--raw-output", "--raw-input", "--slurp"], [], writtenProgram(path), '"$1"');
  return [
    ...reading(names.cost, cost.value.path),
    ...(currency === undefined ? [] : ["", ...reading(names.currency, currency.value.path)]),
    "",
  ];
}

/**
 * Reading, pinning and converting a cost read off the response, in that
 * order, before anything is built: each refusal returns before a request
 * exists. Leaves the micros in `_ubb_micros_<field>`, and a currency read
 * beside it pinned in `_ubb_pinned_currency`.
 */
function readCost(call: CallPlan, report: string): string[] {
  const cost = scalarOf(call, "response_cost");
  if (cost === undefined) return [];
  const currency = scalarOf(call, "response_currency");
  const names = readProgramNames(call);
  const refused = status(SHELL_EXIT.valueRefused);
  const from = `"$${shVariable(cost.value.parameter.name)}"`;
  const read = (name: string, field: Cost, helper: string, path: readonly string[]) => [
    ...asComments(field.comments, I1),
    `${I1}_ubb_read=$(${programName(name)} ${from}) || return ${refused}`,
    `${I1}${helper} ${report} ${field.name} ${shWord(jqLiteral([...path]))} || return $?`,
  ];
  return [
    ...read(names.cost, cost.field, "_ubb_read_amount", cost.value.path),
    ...(currency === undefined
      ? [`${I1}_ubb_pin_currency ${shWord(cost.value.declared)} '' || return $?`]
      : [
          ...read(names.currency, currency.field, "_ubb_read_currency", currency.value.path),
          `${I1}_ubb_pin_currency '' "$_ubb_reported" || return $?`,
          `${I1}_ubb_pinned_currency=$_ubb_currency`,
        ]),
    `${I1}_ubb_to_micros "$_ubb_amount" ${shWord(cost.value.representation)} "$_ubb_currency" || return $?`,
    `${I1}_ubb_micros_${wireName(cost.field.name)}=$_ubb_micros`,
  ];
}

/** Each field the shell writes into a call's body, as the line that writes
 * it in: a converted cost as its digits, and a pinned currency as a code
 * from the closed table. Neither is ever a jq number or jq text. */
function splices(call: CallPlan): string[] {
  const written = (name: string, value: string) =>
    `${I1}_ubb_body="{\\"${wireName(name)}\\":${value},\${_ubb_body#?}"`;
  const cost = scalarOf(call, "response_cost");
  const currency = scalarOf(call, "response_currency");
  return [
    ...costs(call).map(({ field }) => written(field.name, `$_ubb_micros_${wireName(field.name)}`)),
    ...(cost === undefined ? [] : [written(cost.field.name, `$_ubb_micros_${wireName(cost.field.name)}`)]),
    ...(currency === undefined ? [] : [written(currency.field.name, `\\"$_ubb_pinned_currency\\"`)]),
  ];
}

/** Whether the program `lines` reads the jq variable of `parameter`. */
function readsTheParameter(lines: readonly string[], parameter: Parameter): boolean {
  const variable = new RegExp(`\\$${jqVariable(parameter.name)}(?![A-Za-z0-9_])`);
  return lines.some((line) => variable.test(line));
}

function path(call: CallPlan): string {
  // Fixed text as the contract spells it, and the value of a parameter where
  // the route has a place.
  const filled = routeWith(call, (parameter) => `'"$${shVariable(parameter.name)}"'`);
  return `'${filled}'`.replace(/''$/, "").replace(/^''/, "");
}

/** What a call does with the response it was answered with. */
function ending(call: CallPlan): string[] {
  switch (call.kind) {
    case "start":
      // A new Task: whatever stop the last one met is not its own.
      return [
        `${I1}_ubb_started || return $?`,
        `${I1}${SHELL_FILE.stopRequested}=`,
        `${I1}_ubb_stop_met=`,
      ];
    case "subtask":
      return [`${I1}_ubb_started`];
    case "record":
      // Called as a plain command and last, so the status it returns — the
      // stop's, where there is one — is the status of the record itself.
      return [`${I1}_ubb_acknowledge "$${shVariable(call.sentUnder!.name)}"`];
    case "close":
      return [`${I1}_ubb_closed="$_ubb_closed $${shVariable(call.closes!.name)}"`];
  }
}

function callFunction(uses: Uses, call: CallPlan, comments: readonly string[]): string[] {
  const converted = costs(call);
  const readOff = scalarOf(call, "response_cost") !== undefined;
  if (converted.length > 0 || readOff) {
    uses.reportedCost = true;
    uses.callerCost ||= converted.length > 0;
    uses.responseRead ||= readOff;
    uses.currencyRead ||= scalarOf(call, "response_currency") !== undefined;
    if (!call.body.some((field) => !givenOnly(field) && sent(field))) {
      refuse(`the call ${call.name} sends nothing but a converted cost`);
    }
  }
  const tail = ending(call);
  // Named for the call it is the body of, without the prefix every call has.
  const body = `body_${callTail(call)}`;
  const lines = bodyProgram(call);
  return [
    ...readPrograms(call),
    ...program(
      body,
      ["--compact-output", "--null-input"],
      // Only what the program reads: a response a cost is read off and no
      // quantity is, is never parsed again here.
      call.parameters
        .filter((parameter) => readsTheParameter(lines, parameter))
        .flatMap((parameter) => binding(parameter) ?? []),
      lines,
    ),
    "",
    ...asComments(comments),
    `${call.name}() {`,
    // What a call that can meet a stop leaves in the variable is its own
    // result: an earlier call's stop is cleared before anything else is done.
    ...(call.kind === "record" ? [`${I1}${SHELL_FILE.stopRequested}=`] : []),
    ...guard(uses, call),
    `${I1}_ubb_preflight || return $?`,
    `${I1}_ubb_environment || return $?`,
    ...readArguments(call),
    ...checks(uses, call),
    ...converted.flatMap(({ field, value }) => [
      ...asComments(field.comments, I1),
      `${I1}_ubb_pin_currency ${shWord(value.declared)} '' || return $?`,
      `${I1}_ubb_to_micros "$${shVariable(value.parameter.name)}" ${shWord(value.representation)} "$_ubb_currency" || return $?`,
      `${I1}_ubb_micros_${wireName(field.name)}=$_ubb_micros`,
    ]),
    ...readCost(call, call.name),
    // Where jq cannot build the body, what it was handed is why: a response
    // that does not hold what a declared path reads, or is not one.
    ...capture("_ubb_body", body, [], [`return ${status(SHELL_EXIT.valueRefused)}`]),
    // A converted cost is written into the body as its digits, and a pinned
    // currency as its code, by the shell: a cost never becomes a jq number,
    // which could not hold all of them.
    ...splices(call),
    `${I1}_ubb_post ${path(call)} "$_ubb_body" || return $?`,
    ...tail,
    "}",
  ];
}

function runTask(): string[] {
  const usage = status(SHELL_EXIT.usage);
  const name = SHELL_FILE.runTask;
  const closed = (then: string) => [
    `${I1}case " $_ubb_closed " in`,
    `${I2}*" $2 "*) ${then} ;;`,
    `${I1}esac`,
  ];
  return [
    ...asComments(SHELL_COMMENTS.runTask),
    `${name}() {`,
    // It returns a stop's status too, so the stop it leaves is its own: an
    // earlier one is cleared before anything that could refuse the run.
    `${I1}${SHELL_FILE.stopRequested}=`,
    `${I1}_ubb_stop_met=`,
    `${I1}[ "$#" -ge 1 ] || {`,
    `${I2}printf '%s: %s\\n' ${name} ${shWord(SHELL_MESSAGES.work)} >&2`,
    `${I2}return ${usage}`,
    `${I1}}`,
    `${I1}_ubb_work=$1`,
    `${I1}shift`,
    `${I1}${SHELL_FILE.startTask} "$@" || return $?`,
    // The command, the id of the work and then the status it ended with are
    // kept in the function's own arguments: the one place a shell function
    // has that a function it calls cannot write over.
    `${I1}set -- "$_ubb_work" "$${SHELL_FILE.taskId}"`,
    `${I1}"$1" "$2" && set -- "$1" "$2" 0 || set -- "$1" "$2" "$?"`,
    // A stop the work met is acted on here whatever the work then returned:
    // one whose status was never checked is still a stop, and is not success.
    `${I1}if [ "$3" -eq ${STOP} ] || [ -n "$_ubb_stop_met" ]; then`,
    // This call's own result: the stop its Task met, whatever a later call
    // inside the work left in the variable.
    `${I2}${SHELL_FILE.stopRequested}=$_ubb_stop_met`,
    `${I2}${say(SHELL_MESSAGES.stop)}`,
    `${I2}printf '%s %s\\n' ${SHELL.stopMetadata} "\${${SHELL_FILE.stopRequested}:-null}" >&2`,
    `${I2}return ${STOP}`,
    `${I1}fi`,
    ...closed('return "$3"'),
    `${I1}if [ "$3" -eq 0 ]; then`,
    `${I2}printf '%s: %s\\n' ${name} ${shWord(SHELL_MESSAGES.outcomeRequired)} >&2`,
    `${I2}return ${usage}`,
    `${I1}fi`,
    // A status is not evidence of how the work went: a failure, a signal's
    // among them, is passed on as it is and no outcome is declared for it.
    `${I1}printf '%s: %s\\n' ${name} ${shWord(SHELL_MESSAGES.leftOpen)} >&2`,
    `${I1}return "$3"`,
    "}",
  ];
}

// ---------------------------------------------------------------------------
// The file
// ---------------------------------------------------------------------------

function section(...blocks: (readonly string[])[]): string[] {
  return blocks.flatMap((block) => (block.length === 0 ? [] : ["", ...block]));
}

/** The runnable file's text. */
export function renderModule(plan: Plan): string {
  const uses: Uses = {
    notReady: false,
    reportedCost: false,
    callerCost: false,
    responseRead: false,
    currencyRead: false,
    wholeNumber: false,
    urlValue: false,
  };

  const pricingMode = factOfField(plan.start.call, FIELD.kindOfWork, FACT.pricingMode);
  const sold = typeof pricingMode === "string" ? (PRICING_MODE_COMMENTS[pricingMode] ?? []) : [];
  const start = callFunction(uses, plan.start, [...COMMENTS.start, ...sold]);
  const subtasks = plan.subtasks.map((subtask) => callFunction(uses, subtask, COMMENTS.subtask));
  const records = plan.records.map((record) =>
    callFunction(uses, record, [
      ...SHELL_COMMENTS.record,
      ...(record.parameters.some((parameter) => parameter.use === "file")
        ? SHELL_COMMENTS.response
        : []),
    ]),
  );
  const close = callFunction(uses, plan.close, SHELL_COMMENTS.close);

  // Everything after preflight, first: what preflight probes for is read off
  // the programs these hold.
  const after = [
    environment(plan),
    request(plan),
    started(),
    acknowledgement(),
    parameterHelpers(uses),
    uses.notReady ? notReadyHelper() : [],
    uses.reportedCost ? reportedCostHelpers(uses.callerCost) : [],
    uses.responseRead ? readHelpers(uses.currencyRead) : [],
    start,
    runTask(),
    ...subtasks,
    ...records,
    close,
  ];
  const lines = [
    ...headerText(plan.header, plan.calls, SHELL_READINESS_COMMENTS, [
      ...SHELL_COMMENTS.legend,
      "",
      ...SHELL_COMMENTS.usage,
    ]).map((line) => (line === "" ? "" : `# ${line}`)),
    ...section(constants(), preflight(jqNeedsOf(after.flat().join("\n"))), ...after),
  ];
  return `${lines.join("\n")}\n`;
}
