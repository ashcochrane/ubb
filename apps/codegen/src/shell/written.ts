/**
 * Reading a value off a supplier's response AS THE RESPONSE WROTE IT (#583).
 *
 * A supplier's cost is money, and a binary float is refused (#193 §D5): an
 * integer or a decimal string is read, and a number written with a fraction
 * or an exponent is not. Python's `json` tells the two apart by how the
 * number is WRITTEN — `1` is an int, and `1.0` and `1e0` are floats — and a
 * shell file must answer every case the same way (the owner's ruling of
 * 2026-10-08 on #583). jq cannot be asked: every jq parses a number into a
 * value, and the value has lost the spelling. jq 1.5 and 1.6 print `1.0`,
 * `1e0` and `1.5e1` as `1`, `1` and `15`; jq 1.7 and 1.8 keep `1.0` but
 * still print `1e0` as `1` and `1.5e1` as `15`, and 1.5 and 1.6 round an
 * integer past fifteen digits besides.
 *
 * So the response is read as TEXT (`--raw-input --slurp`) and parsed once for
 * its structure. The text is then split at its quotes (a quote is escaped by
 * the parity of the backslashes before it), which tells what is inside a
 * string from what is not. Outside the strings, whitespace is dropped — JSON
 * never separates two values by whitespace alone — and each of `,:[]{}` is
 * marked with U+0001, which no JSON text holds outside a string, so every run
 * between two marks is one scalar.
 *
 * FIRST, A NUMBER PYTHON'S `json` DOES NOT READ IS NOT READ, WHEREVER IT
 * SITS. jq reads numbers JSON does not allow: `+1`, `01`, `.5` or `1.`, `nan`
 * and `inf` in any spelling, a number with a NUL after it, and (jq 1.5 and
 * 1.6) a NUL inside a string. Python reads `NaN`, `Infinity` and `-Infinity`,
 * and none of the others. So with those three words and JSON's three taken
 * out, a scalar holding anything a number Python reads never holds
 * (`NOT_PYTHONS`) makes the whole response unreadable. This is targeted at
 * those spellings, not an implementation of Python's whole parser: it is no
 * promise that the file accepts exactly the documents Python accepts. The
 * invariant is narrower — at the declared paths, both targets give a value
 * the same meaning, and neither ever takes a number written with a fraction
 * or an exponent for an exact reported cost (ADR-0017 §6).
 *
 * THEN, where the value at the path is a number, jq parses a COPY of the text
 * in which every scalar outside a string is written as a JSON string of its
 * own characters. The copy has the response's structure, so the same path
 * finds in it the number exactly as written, and it is read iff it is a JSON
 * integer: `-?(0|[1-9][0-9]*)`.
 *
 * The work over the whole text is jq's own `split` and `add`, which every jq
 * runs in C, and `join` is never used: it is quadratic on every jq measured.
 * The program looks at characters one by one in two places only: a part of
 * the text that ends in a backslash, to count them, and the token at the
 * path.
 *
 * Measured against jq 1.4, 1.5, 1.6, 1.7.1 and 1.8.1 and gojq 0.12.17, with
 * `json.loads` as the oracle — see ADR-0017 §6 for the forms, the documents,
 * the read's cost, and the whole-document parser differences that remain as
 * the target's limitations. jq 1.4 cannot compile the program (it has no
 * `foreach`), which the probe, derived from this text, refuses before
 * anything is sent.
 *
 * What the program prints is ONE answer and never an error of its own: the
 * kind of what is at the path, and for a string or an integer `:` and its
 * text — `string:1.25`, `integer:1230`, `float`, `flag`, `null`, `missing`,
 * `other`, `unreadable`. What each kind means for the call is the shell's to
 * say, in the catalogue's words.
 */
import { MESSAGES, SHELL_COMMENTS, SHELL_EXIT, SHELL_MESSAGES } from "../catalogue.ts";
import { asComments } from "../comments.ts";
import { INDENT, jqLiteral, jqString, shWord } from "./syntax.ts";

const I1 = INDENT;
const I2 = INDENT.repeat(2);
const I3 = INDENT.repeat(3);

/** What marks a structural character in the copy: one no JSON text holds
 * outside a string. */
const MARK = String.fromCharCode(1);

/** The characters that separate the scalars of a JSON text, outside its
 * strings. */
const STRUCTURE = [",", ":", "[", "]", "{", "}"];
const WHITESPACE = [" ", "\t", "\n", "\r"];

/** The scalars Python's `json` reads that are not numbers: JSON's three
 * words, and the three it adds. */
const WORDS = ["true", "false", "null", "NaN", "Infinity", "-Infinity"];

/**
 * The numbers jq reads outside a string and Python's `json` does not, once
 * the words are taken out and each scalar sits between two marks. jq hands
 * every other character outside a string to its number reader, which takes
 * a sign of `+`, leading zeros, a point with no digit on one side (`.5`,
 * `1.`), `nan` and `inf` spelled every way, and a number with a NUL after it,
 * where its C reader stops; Python takes none of them. So: any letter but an
 * exponent's, a parenthesis, a NUL, a byte-order mark, and the five shapes a
 * number Python reads never has.
 */
const NOT_PYTHONS: readonly string[] = [
  ..."abcdfghijklmnopqrstuvwxyzABCDFGHIJKLMNOPQRSTUVWXYZ()",
  "\u0000",
  "\ufeff",
  `${MARK}+`,
  `${MARK}.`,
  `${MARK}-.`,
  `.${MARK}`,
  ".e",
  ".E",
  ..."0123456789".split("").flatMap((digit) => [`${MARK}0${digit}`, `${MARK}-0${digit}`]),
];

/** A jq string literal, with a byte-order mark escaped rather than written
 * into the file as itself. */
function q(text: string): string {
  return jqString(text).replace(/\ufeff/g, "\\ufeff");
}

/** The kinds the program answers with; the first two carry the text. */
export const KIND = {
  string: "string",
  integer: "integer",
  float: "float",
  flag: "flag",
  null: "null",
  missing: "missing",
  other: "other",
  unreadable: "unreadable",
} as const;

/** The jq program that reads the value at `path` off a response file. */
export function writtenProgram(path: readonly string[]): string[] {
  const at = jqLiteral([...path]);
  const parts = (inside: boolean) =>
    `[range(0; $parts | length) as $at | if $inside[$at] then ${inside ? "$parts[$at]" : "empty"} ` +
    `else ${inside ? "empty" : "$parts[$at]"} end] | add // ""`;
  return [
    ...SHELL_COMMENTS.writtenProgram.map((line) => `# ${line}`),
    "def ubb_escapes_next:",
    `${I1}if endswith(${q("\\")}) then`,
    `${I2}explode as $c`,
    `${I2}| ([range(0; $c | length) | select($c[.] != 92)] | last) as $kept`,
    `${I2}| ((($c | length) - (if $kept == null then 0 else $kept + 1 end)) % 2) == 1`,
    `${I1}else false end;`,
    "def ubb_inside_flags:",
    `${I1}[foreach .[] as $part ([false, false];`,
    `${I2}[.[1], (if .[1] then ($part | ubb_escapes_next) else true end)];`,
    `${I2}.[0])];`,
    "def ubb_without($character):",
    `${I1}split($character) | add // "";`,
    "def ubb_marked($character):",
    `${I1}split($character)`,
    `${I1}| if length == 0 then ""`,
    `${I2}else [.[0], (.[1:][] | (${q(MARK)} + $character + ${q(MARK)}), .)] | add end;`,
    "def ubb_scalars_quoted:",
    `${I1}${WHITESPACE.map((space) => `ubb_without(${q(space)})`).join(" | ")}`,
    `${I1}| ${STRUCTURE.map((mark) => `ubb_marked(${q(mark)})`).join(" | ")}`,
    `${I1}| split(${q(MARK)})`,
    `${I1}| map(if ${["", ...STRUCTURE].map((kept) => `. == ${q(kept)}`).join(" or ")}`,
    `${I2}then . else ${q('"')} + . + ${q('"')} end)`,
    `${I1}| add // "";`,
    "def ubb_as_written($parts; $inside):",
    `${I1}[range(0; $parts | length) as $at`,
    `${I2}| (if $at > 0 then ${q('"')} else empty end),`,
    `${I2}  (if $inside[$at] then $parts[$at] else ($parts[$at] | ubb_scalars_quoted) end)]`,
    `${I1}| add;`,
    "def ubb_python_reads($parts; $inside):",
    `${I1}(${parts(false)}`,
    `${I2}| ${WHITESPACE.map((space) => `ubb_without(${q(space)})`).join(" | ")}`,
    `${I2}| ${STRUCTURE.map((mark) => `ubb_marked(${q(mark)})`).join(" | ")}`,
    `${I2}| ${q(MARK)} + . + ${q(MARK)}`,
    `${I2}| ${WORDS.map((word) => `ubb_without(${q(`${MARK}${word}${MARK}`)})`).join(" | ")}) as $scalars`,
    `${I1}| (${parts(true)}) as $strings`,
    `${I1}| ([[${NOT_PYTHONS.map(q).join(", ")}][]`,
    `${I2}| select(. as $pattern | $scalars | split($pattern) | length > 1)] | length) == 0`,
    `${I1}and ($strings | split(${q("\u0000")}) | length) < 2;`,
    "def ubb_at($path):",
    `${I1}reduce $path[] as $segment ({"found": true, "value": .};`,
    `${I2}if .found and (.value | type) == "object" and (.value | has($segment))`,
    `${I2}then {"found": true, "value": .value[$segment]}`,
    `${I2}else {"found": false, "value": null} end);`,
    "def ubb_whole:",
    `${I1}explode`,
    `${I1}| (if .[0] == 45 then .[1:] else . end)`,
    `${I1}| length > 0 and (map(select(. < 48 or . > 57)) | length) == 0`,
    `${I1}  and (length == 1 or .[0] != 48);`,
    ". as $text",
    "| (try [fromjson] catch null) as $parsed",
    `| if $parsed == null then ${q(KIND.unreadable)}`,
    `${I1}else ($text | split(${q('"')})) as $parts`,
    `${I1}| ($parts | ubb_inside_flags) as $inside`,
    `${I1}| if (ubb_python_reads($parts; $inside) | not) then ${q(KIND.unreadable)}`,
    `${I1}else ($parsed[0] | ubb_at(${at})) as $found`,
    `${I1}| ($found.value | type) as $type`,
    `${I1}| if ($found.found | not) then ${q(KIND.missing)}`,
    `${I2}elif $type == "null" then ${q(KIND.null)}`,
    `${I2}elif $type == "boolean" then ${q(KIND.flag)}`,
    `${I2}elif $type == "string" then`,
    // No shell variable holds a NUL, and Python's conversion refuses one.
    `${I3}(if ($found.value | explode | map(select(. == 0)) | length) > 0`,
    `${I3} then ${q(KIND.other)} else ${q(`${KIND.string}:`)} + $found.value end)`,
    `${I2}elif $type == "number" then`,
    `${I3}(try [ubb_as_written($parts; $inside) | fromjson] catch null) as $copy`,
    `${I3}| (if $copy == null then null else ($copy[0] | ubb_at(${at})).value end) as $token`,
    `${I3}| if ($token | type) == "string" and ($token | ubb_whole)`,
    `${I3}  then ${q(`${KIND.integer}:`)} + $token else ${q(KIND.float)} end`,
    `${I2}else ${q(KIND.other)} end`,
    `${I1}end`,
    "end",
  ];
}

/**
 * The two shell functions that act on what a program answered, left in
 * `_ubb_read`: each sets its value and returns 0, or says why it refused and
 * returns UBB_EXIT_VALUE_REFUSED. Called with the call, the field and the
 * declared path as JSON, which is printed with the refusal. The currency's
 * function, and the words about it, only in a file that reads a currency.
 */
export function readHelpers(currencyRead: boolean): string[] {
  const refused = `"$${SHELL_EXIT.valueRefused.name}"`;
  const refusal = [
    `${I1}printf '%s: %s read at %s %s\\n' "$1" "$2" "$3" "$_ubb_why" >&2`,
    `${I1}return ${refused}`,
  ];
  const why = (kind: string, message: string) => `${I2}${kind}) _ubb_why=${shWord(message)} ;;`;
  const currency = [
    "",
    "_ubb_read_currency() {",
    `${I1}case $_ubb_read in`,
    `${I2}${KIND.string}:*)`,
    `${I3}_ubb_reported=\${_ubb_read#*:}`,
    `${I3}return 0`,
    `${I3};;`,
    why(KIND.missing, SHELL_MESSAGES.readMissing),
    why(KIND.unreadable, SHELL_MESSAGES.readUnreadable),
    why("*", MESSAGES.currencyNotText),
    `${I1}esac`,
    ...refusal,
    "}",
  ];
  return [
    ...asComments([
      ...SHELL_COMMENTS.responseCost,
      ...(currencyRead ? SHELL_COMMENTS.responseCurrency : []),
    ]),
    "_ubb_read_amount() {",
    `${I1}case $_ubb_read in`,
    `${I2}${KIND.string}:* | ${KIND.integer}:*)`,
    `${I3}_ubb_amount=\${_ubb_read#*:}`,
    `${I3}return 0`,
    `${I3};;`,
    why(KIND.missing, SHELL_MESSAGES.readMissing),
    why(KIND.unreadable, SHELL_MESSAGES.readUnreadable),
    why(KIND.null, SHELL_MESSAGES.readNull),
    why(KIND.flag, MESSAGES.flag),
    why(KIND.float, MESSAGES.floatRead),
    why("*", MESSAGES.notANumber),
    `${I1}esac`,
    ...refusal,
    "}",
    ...(currencyRead ? currency : []),
  ];
}
