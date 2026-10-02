/**
 * Writing a value on one line of a file, whatever the file is.
 *
 * Target-neutral: a comment in a Python file and a comment in a shell file
 * state a value the same way, as one line of JSON. What a TARGET's own
 * literals look like is that target's business and is not here.
 */
import { refuse, type Json } from "./blueprint.ts";

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

function unicodeEscape(codeUnit: number): string {
  return `\\u${codeUnit.toString(16).padStart(4, "0")}`;
}

function onOneLine(text: string): string {
  return Array.from(text, (character) =>
    endsALine(character.charCodeAt(0)) ? unicodeEscape(character.charCodeAt(0)) : character,
  ).join("");
}

/**
 * A number as the document meant it, or a refusal. Past 2**53 a whole number
 * was already rounded on its way into this process, and writing the rounded
 * figure down would state one nobody declared.
 */
export function exactly(value: number): number {
  if (Number.isInteger(value) && !Number.isSafeInteger(value)) {
    return refuse(`${value} is a whole number too large to be carried exactly`);
  }
  return value;
}

function everyNumberIsExact(value: Json): void {
  if (typeof value === "number") exactly(value);
  else if (Array.isArray(value)) (value as readonly Json[]).forEach(everyNumberIsExact);
  else if (value !== null && typeof value === "object") {
    Object.values(value as { readonly [key: string]: Json }).forEach(everyNumberIsExact);
  }
}

/**
 * A value as one line of JSON. One line whatever it holds: JSON escapes most
 * control characters itself, and the ones it leaves alone are escaped here,
 * in JSON's own form, so the line still parses as the value.
 */
export function oneLineJson(value: Json): string {
  everyNumberIsExact(value);
  return onOneLine(JSON.stringify(value));
}

/** A name as itself, unless a character in it could end the line. */
export function oneLineName(name: string): string {
  return onOneLine(name);
}
