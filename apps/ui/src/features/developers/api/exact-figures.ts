// A stop's two figures, read off a Verify answer's TEXT exactly (#585).
//
// The platform publishes `stop_bound_micros` and `stop_measured_micros` as
// JSON integers, bounded by nothing narrower than the signed 64-bit money
// column each is kept in (ADR-0019 §1; `StopAcknowledgement`'s columns are
// `BigIntegerField`). Nothing in the contract caps a COGS ceiling, a Pool's
// cap or a minimum balance, so a tenant may declare one past 2^53, and a
// wallet's balance or a Pool's month-to-date charges can come to one.
// `JSON.parse` makes every number a double, which holds an integer exactly
// only up to 2^53: a legal figure would be rounded before anything on the
// page could format it, and no formatter can give the digits back.
//
// So the text is read twice: by `JSON.parse`, for everything, and as a copy
// in which every number outside a string is written as a JSON string of its
// own characters — the read ADR-0017 §6 does in jq, done here in TypeScript.
// The copy has the answer's structure, so each figure is taken from the copy:
// the digits UBB wrote. A figure that is not a JSON integer is refused rather
// than rounded, filled or dropped, as the generated shell file refuses one
// (ADR-0017 §4). Every other number is left as `JSON.parse` read it.

import { isExactMicros } from "@/lib/format";

import type { BlueprintVerification } from "./types";

/** The two figures a stop is measured by, wherever an answer carries them. */
const FIGURES: ReadonlySet<string> = new Set(["stop_bound_micros", "stop_measured_micros"]);

/** A JSON number, read from where one starts. */
const NUMBER = /-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?/y;

const isObject = (value: unknown): value is object => typeof value === "object" && value !== null;

/**
 * `text` with every number outside a string written as a JSON string of its
 * own characters, and nothing else changed. `text` must already be JSON: then
 * a string is told by its quotes (a backslash escapes the one character after
 * it), and outside one a number is the only thing that starts with `-` or a
 * digit.
 */
export function withNumbersAsText(text: string): string {
  let copy = "";
  let at = 0;
  while (at < text.length) {
    const character = text[at]!;
    if (character === '"') {
      let end = at + 1;
      while (end < text.length && text[end] !== '"') end += text[end] === "\\" ? 2 : 1;
      copy += text.slice(at, end + 1);
      at = end + 1;
    } else if (character === "-" || (character >= "0" && character <= "9")) {
      NUMBER.lastIndex = at;
      const [token] = NUMBER.exec(text) ?? [character];
      copy += `"${token}"`;
      at += token.length;
    } else {
      copy += character;
      at += 1;
    }
  }
  return copy;
}

/** Every stop figure in `parsed` replaced by its token in `written`, in place.
 * A figure is null, or a JSON integer; anything else is refused. */
function carryFigures(parsed: unknown, written: unknown): void {
  if (!isObject(parsed) || !isObject(written)) return;
  for (const [key, value] of Object.entries(parsed)) {
    const token: unknown = Reflect.get(written, key);
    if (!FIGURES.has(key)) {
      carryFigures(value, token);
    } else if (value !== null) {
      if (typeof value !== "number" || !isExactMicros(token)) {
        const as = typeof value === "number" ? String(token) : JSON.stringify(value);
        throw new Error(`${key} is not a whole number of micros: ${as}`);
      }
      Reflect.set(parsed, key, token);
    }
  }
}

/**
 * The JSON `text`, parsed, with every stop figure in it the decimal integer
 * UBB wrote rather than the number `JSON.parse` makes of it. A null stays
 * null. Throws for a figure written as anything but a whole number.
 */
export function readWithExactFigures(text: string): unknown {
  const parsed: unknown = JSON.parse(text);
  carryFigures(parsed, JSON.parse(withNumbersAsText(text)));
  return parsed;
}

/**
 * A Verify answer, read off its text with its stop figures exact. The
 * contract types the rest of the answer, as it does every body the client
 * parses; this read changes only how the two figures are held, which
 * `BlueprintVerification` states.
 */
export function verificationFromText(text: string): BlueprintVerification {
  return readWithExactFigures(text) as BlueprintVerification;
}
