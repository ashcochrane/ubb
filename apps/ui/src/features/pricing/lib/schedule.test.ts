import { describe, expect, it } from "vitest";

import { ApiProblem } from "@/api/problem";
import {
  SCHEDULE_REFUSALS,
  effectiveInstant,
  isScheduleRefusal,
  scheduleRefusal,
  type ScheduleRefusalCode,
} from "./schedule";

function refusal(code: string, detail: string): ApiProblem {
  return new ApiProblem({
    status: 422,
    code,
    title: "Validation error",
    detail,
  });
}

describe("a refused effective instant", () => {
  // ⚠ THE FOUR ARE FOUR DIFFERENT ANSWERS, AND THAT IS WHY THEY HAVE FOUR
  // CODES. `core/scheduling` coins them so that "that date is a typo" is
  // distinguishable from "that date has passed"; a console that rendered one
  // sentence for all four would throw away the distinction at the last step.
  it("gives every named code a sentence of its own", () => {
    const sentences = Object.values(SCHEDULE_REFUSALS);

    expect(new Set(sentences).size).toBe(sentences.length);
    expect(sentences).toHaveLength(4);
  });

  it("names the platform horizon when the date is beyond it", () => {
    const shown = scheduleRefusal(
      refusal("effective_at_too_far_ahead", "effective_at is more than 366 days ahead."),
    );

    expect(shown).toBe(SCHEDULE_REFUSALS.effective_at_too_far_ahead);
    expect(shown).toContain("366");
  });

  it("tells a boundary conflict apart from a date in the past", () => {
    expect(scheduleRefusal(refusal("effective_at_in_past", "x"))).not.toBe(
      scheduleRefusal(refusal("effective_at_before_scheduled_boundary", "x")),
    );
  });

  // ⚠ KEYED ON THE CODE AND NEVER ON THE TEXT. The server's detail is prose and
  // prose gets edited; the code is the contract. A matcher reading the sentence
  // would fall through to the generic message the day somebody improves it —
  // silently, and on exactly the refusal a tenant most needs told apart.
  it("recognises a code whose detail says something else entirely", () => {
    const reworded = refusal(
      "effective_at_too_far_ahead",
      "some future rewording of this message",
    );

    expect(isScheduleRefusal(reworded)).toBe(true);
    expect(scheduleRefusal(reworded)).toBe(
      SCHEDULE_REFUSALS.effective_at_too_far_ahead,
    );
  });

  it("falls back to the server's own message for anything else", () => {
    const other = refusal("validation_error", "measurement_key is required.");

    expect(isScheduleRefusal(other)).toBe(false);
    expect(scheduleRefusal(other)).toBe("measurement_key is required.");
  });

  it("says something sensible for a failure that is not a problem at all", () => {
    expect(scheduleRefusal(new Error("network down"))).toBe("network down");
    expect(scheduleRefusal(undefined)).toBe("Something went wrong.");
  });

  // The vacuity guard: a lookup built over a plain object would answer for
  // `toString` and `constructor` too, and then every unrecognised failure would
  // render a function body at a tenant.
  it("does not treat an inherited property name as a refusal code", () => {
    for (const inherited of ["toString", "constructor", "hasOwnProperty"]) {
      expect(isScheduleRefusal(refusal(inherited, "x"))).toBe(false);
    }
  });

  it("every declared code resolves to its own sentence", () => {
    for (const code of Object.keys(SCHEDULE_REFUSALS) as ScheduleRefusalCode[]) {
      expect(scheduleRefusal(refusal(code, "ignored"))).toBe(SCHEDULE_REFUSALS[code]);
    }
  });
});

describe("the instant a dated change names", () => {
  it("sends nothing at all for an unset date, which is what NOW means", () => {
    expect(effectiveInstant("")).toBeUndefined();
  });

  it("sends the instant a complete date names", () => {
    expect(effectiveInstant("2027-01-15T09:30")).toBe(
      new Date("2027-01-15T09:30").toISOString(),
    );
  });

  // ⚠ THE BUG THIS FUNCTION EXISTS TO HAVE FIXED. Two screens each derived
  // this for themselves and only one guarded the parse, so on the other a
  // half-typed date reached `new Date(...).toISOString()` and threw
  // `RangeError` — while the tenant was still typing, on a form they had not
  // submitted. A partial value is "not stated", not a crash.
  it("treats a half-typed date as not stated rather than throwing", () => {
    // ⚠ THE PROPERTY IS "NEVER THROWS", AND IT IS ASSERTED OVER EVERYTHING a
    // half-finished field can hold. What each partial then RESOLVES to is the
    // engine's business rather than this module's — `2027-` and `2027-01-1` are
    // both dates V8 reads happily, which is exactly why a console cannot decide
    // "looks incomplete" for itself and why the guard is on the parse result.
    const partials = ["2027-", "2027-01-1", "2027-01-15T0", "not a date", "!!"];
    for (const partial of partials) {
      expect(() => effectiveInstant(partial)).not.toThrow();
    }
    // The ones that genuinely name no moment come back as "not stated".
    for (const nonsense of ["not a date", "!!"]) {
      expect(effectiveInstant(nonsense)).toBeUndefined();
    }
  });
});
