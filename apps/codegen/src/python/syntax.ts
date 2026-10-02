/**
 * Python's own spelling of a value: literals, identifiers and names.
 *
 * A declared name is the tenant's word and may be anything a registry admits
 * — an apostrophe, a dollar sign, a backslash, a line of another alphabet. It
 * is written into a file as a string literal and never as anything else, and
 * this module is the only place a literal is spelled, so there is one
 * escaping rule and it is applied to every one of them.
 */
import { refuse, type Json } from "../blueprint.ts";
import { endsALine, exactly } from "../text.ts";

/** One level of indentation in a generated file. */
export const INDENT = "    ";

const HARD_KEYWORDS = new Set([
  "False", "None", "True", "and", "as", "assert", "async", "await", "break",
  "class", "continue", "def", "del", "elif", "else", "except", "finally",
  "for", "from", "global", "if", "import", "in", "is", "lambda", "nonlocal",
  "not", "or", "pass", "raise", "return", "try", "while", "with", "yield",
]);

const IDENTIFIER = /^[A-Za-z_][A-Za-z0-9_]*$/;

/** Whether `name` can be written as a Python name: reached by attribute
 * access, or bound as a parameter. */
export function isIdentifier(name: string): boolean {
  return IDENTIFIER.test(name) && !HARD_KEYWORDS.has(name);
}

/** A parameter the Blueprint names, used exactly as given — or a refusal. */
export function parameterName(name: string): string {
  if (!isIdentifier(name)) {
    return refuse(`the parameter name ${JSON.stringify(name)} is not one Python can bind`);
  }
  return name;
}

function escaped(codeUnit: number): string {
  if (codeUnit < 0x100) return `\\x${codeUnit.toString(16).padStart(2, "0")}`;
  return `\\u${codeUnit.toString(16).padStart(4, "0")}`;
}

/**
 * `text` as a Python string literal that means exactly `text`.
 *
 * Double-quoted, so an apostrophe needs nothing. The backslash and the quote
 * are escaped, and so is every character that would end the line the literal
 * sits on or that a file cannot hold: the control characters, the three
 * line separators outside ASCII, and an unpaired surrogate. Everything else
 * — any other alphabet, a dollar sign, a backtick, a brace — is written as
 * itself, because nothing in a plain string literal gives it a meaning.
 */
export function pyString(text: string): string {
  let out = '"';
  for (let index = 0; index < text.length; index += 1) {
    const unit = text.charCodeAt(index);
    const character = text[index]!;
    if (character === "\\") out += "\\\\";
    else if (character === '"') out += '\\"';
    else if (character === "\n") out += "\\n";
    else if (character === "\r") out += "\\r";
    else if (character === "\t") out += "\\t";
    else if (endsALine(unit)) {
      out += escaped(unit);
    } else if (unit >= 0xd800 && unit <= 0xdbff) {
      const next = text.charCodeAt(index + 1);
      if (next >= 0xdc00 && next <= 0xdfff) {
        out += character + text[index + 1]!;
        index += 1;
      } else {
        out += escaped(unit);
      }
    } else if (unit >= 0xdc00 && unit <= 0xdfff) {
      out += escaped(unit);
    } else {
      out += character;
    }
  }
  return `${out}"`;
}

/** A literal of the document as the Python expression that evaluates to it. */
export function pyLiteral(value: Json): string {
  if (value === null) return "None";
  if (value === true) return "True";
  if (value === false) return "False";
  if (typeof value === "number") return String(exactly(value));
  if (typeof value === "string") return pyString(value);
  if (Array.isArray(value)) {
    return `[${(value as readonly Json[]).map(pyLiteral).join(", ")}]`;
  }
  const entries = Object.entries(value as { readonly [key: string]: Json });
  return `{${entries.map(([key, inner]) => `${pyString(key)}: ${pyLiteral(inner)}`).join(", ")}}`;
}

/**
 * `wanted`, or `wanted` with underscores after it until no name in `taken`
 * is spelled the same: a name of this package's own that no declared name
 * can stand in front of.
 */
export function unshadowed(wanted: string, taken: ReadonlySet<string>): string {
  let name = wanted;
  while (taken.has(name)) name += "_";
  return name;
}
