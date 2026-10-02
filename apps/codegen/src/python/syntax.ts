/**
 * Python's own spelling of a value: literals, identifiers and names.
 *
 * A declared name is the tenant's word and may be anything a registry admits
 * — an apostrophe, a dollar sign, a backslash, a line of another alphabet. It
 * is written into a file as a string literal and never as anything else, and
 * this module is the only place a literal is spelled, so there is one
 * escaping rule and it is applied to every one of them.
 */
import { BlueprintNotRenderable, type Json } from "../blueprint.ts";

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
    throw new BlueprintNotRenderable(
      `the parameter name ${JSON.stringify(name)} is not one Python can bind`,
    );
  }
  return name;
}

/**
 * Whether a character could end the line it is written on, or cannot be
 * written at all: the control characters, and the three line separators
 * outside ASCII (U+0085, U+2028, U+2029).
 */
export function endsALine(codeUnit: number): boolean {
  return (
    codeUnit < 0x20 ||
    codeUnit === 0x7f ||
    codeUnit === 0x85 ||
    codeUnit === 0x2028 ||
    codeUnit === 0x2029
  );
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

function pyNumber(value: number): string {
  if (Number.isInteger(value) && !Number.isSafeInteger(value)) {
    // Past 2**53 the document's number was already rounded on the way in,
    // and writing the rounded figure down would state one nobody declared.
    throw new BlueprintNotRenderable(
      `${value} is a whole number too large to be carried exactly`,
    );
  }
  return String(value);
}

/** A literal of the document as the Python expression that evaluates to it. */
export function pyLiteral(value: Json): string {
  if (value === null) return "None";
  if (value === true) return "True";
  if (value === false) return "False";
  if (typeof value === "number") return pyNumber(value);
  if (typeof value === "string") return pyString(value);
  if (Array.isArray(value)) {
    return `[${(value as readonly Json[]).map(pyLiteral).join(", ")}]`;
  }
  const entries = Object.entries(value as { readonly [key: string]: Json });
  return `{${entries.map(([key, inner]) => `${pyString(key)}: ${pyLiteral(inner)}`).join(", ")}}`;
}

/**
 * A value as one line of JSON, for a comment. One line whatever it holds:
 * JSON escapes the control characters, and the three line separators it
 * leaves alone are escaped here.
 */
export function oneLineJson(value: Json): string {
  if (typeof value === "number") pyNumber(value);
  return Array.from(JSON.stringify(value), (character) =>
    endsALine(character.charCodeAt(0)) ? escaped(character.charCodeAt(0)) : character,
  ).join("");
}

/**
 * A name of this package's own that no parameter of the file is spelled
 * like, so a declared name can never stand in front of it.
 */
export function fresh(wanted: string, taken: ReadonlySet<string>): string {
  let name = wanted;
  while (taken.has(name)) name += "_";
  return name;
}

/**
 * A declared key as the tail of a function name: its ASCII letters and
 * digits, and an underscore for everything else. Naming, not translation —
 * the key itself is only ever written as a literal.
 */
export function nameTail(key: string): string {
  return key.replace(/[^A-Za-z0-9]/g, "_");
}

/** Eight hexadecimal digits that are a function of `text` and nothing else. */
export function shortHash(text: string): string {
  let hash = 0x811c9dc5;
  for (let index = 0; index < text.length; index += 1) {
    hash ^= text.charCodeAt(index);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash.toString(16).padStart(8, "0");
}
