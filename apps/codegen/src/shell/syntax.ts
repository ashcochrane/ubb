/**
 * The two languages a shell file is written in, and how a value is spelled
 * in each.
 *
 * A declared name is the tenant's word and may be anything a registry admits.
 * It reaches a shell file in exactly two places, and each has ONE encoder:
 *
 * - **In a jq program**, as a jq string literal (`jqString`). A jq string is a
 *   JSON string, so the JSON encoder is the jq encoder: the quote and the
 *   backslash are escaped, which also means no declared name can open jq's
 *   `\(...)` interpolation. The program itself arrives through a quoted
 *   heredoc, where the shell gives no character a meaning at all.
 * - **In shell code**, as a single-quoted word (`shWord`). Inside single
 *   quotes the shell gives no character a meaning but the quote, and that one
 *   is closed, escaped and reopened.
 *
 * Neither is ever written across a line: every character that could end one
 * is escaped first. A jq literal still means exactly the text. A shell word
 * shows the escape — it is only ever used where a name is PRINTED, or where a
 * value holding such a character could not be valid anyway.
 *
 * A parameter's name is used exactly as the Blueprint gives it, and only
 * behind a prefix: `_ubb_p_<name>` in shell, `$p_<name>` in jq. A parameter
 * named `PATH`, `IFS` or `status` is therefore a variable called
 * `_ubb_p_PATH`, and one named `then` is `$p_then` — no declared name can be
 * a variable the shell or jq already gives a meaning to, or one of this
 * file's own.
 */
import { refuse, type Json } from "../blueprint.ts";
import { endsALine, oneLineJson } from "../text.ts";

/** One level of indentation in a generated file. */
export const INDENT = "  ";

const IDENTIFIER = /^[A-Za-z_][A-Za-z0-9_]*$/;

/** A parameter the Blueprint names, used exactly as given — or a refusal. */
export function parameterName(name: string): string {
  if (!IDENTIFIER.test(name)) {
    return refuse(
      `the parameter name ${JSON.stringify(name)} is not one a shell function can take`,
    );
  }
  return name;
}

/** The shell variable a parameter's value is held in. */
export function shVariable(parameter: string): string {
  return `_ubb_p_${parameter}`;
}

/** The jq variable a parameter's value is bound to. */
export function jqVariable(parameter: string): string {
  return `p_${parameter}`;
}

/** `text` with nothing in it that could end a line, or that a file cannot
 * hold: each such character as `\uXXXX`. */
function onOneLine(text: string): string {
  let out = "";
  for (let index = 0; index < text.length; index += 1) {
    const unit = text.charCodeAt(index);
    const next = text.charCodeAt(index + 1);
    const paired =
      (unit >= 0xd800 && unit <= 0xdbff && next >= 0xdc00 && next <= 0xdfff) ||
      (unit >= 0xdc00 &&
        unit <= 0xdfff &&
        text.charCodeAt(index - 1) >= 0xd800 &&
        text.charCodeAt(index - 1) <= 0xdbff);
    const unpaired = unit >= 0xd800 && unit <= 0xdfff && !paired;
    out +=
      endsALine(unit) || unpaired
        ? `\\u${unit.toString(16).padStart(4, "0")}`
        : text[index]!;
  }
  return out;
}

/**
 * `text` as one shell word: single-quoted, on one line. A line-ending
 * character is shown as its escape, so this is for a name that is printed and
 * for a value no such character could be part of.
 */
export function shWord(text: string): string {
  return `'${onOneLine(text).replaceAll("'", "'\\''")}'`;
}

/** `text` as a jq string literal that means exactly `text`. */
export function jqString(text: string): string {
  return oneLineJson(text);
}

/** A literal of the document as the jq expression that evaluates to it. */
export function jqLiteral(value: Json): string {
  return oneLineJson(value);
}

const WIRE_NAME = /^[a-z_][a-z0-9_]*$/;

/**
 * A request field's name where it is written into JSON text by the shell and
 * not by jq. Only a name that needs no escaping in either language is.
 */
export function wireName(name: string): string {
  if (!WIRE_NAME.test(name)) {
    return refuse(`the field name ${JSON.stringify(name)} cannot be written into a body as text`);
  }
  return name;
}
