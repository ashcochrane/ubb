// A unit of work's ceiling assessment as the console reads and words it
// (#454; moved to `lib/` in #467 when a second feature rendered it).
//
// The two surface tests (`run-detail-page.test.tsx`,
// `utilisation-and-headroom.test.tsx`) render each status from a fixture;
// what is asserted here is the half a surface cannot reach — the wire shapes
// no mock authors, and the words both surfaces compose from.

import { describe, expect, it } from "vitest";

import { ceilingAssessment, completeTotal, incompleteTotal } from "@/lib/economic-scenarios";
import { CEILING_STATUS_VALUES } from "@/lib/vocabulary";

import {
  CEILING_STATUS_EXPLANATIONS,
  ceilingStatusLabel,
  describeCeilingFigures,
  describeHeadroom,
  describeUtilisation,
  explainCeiling,
  readCeiling,
} from "./ceiling";

describe("the words for a ceiling assessment", () => {
  it("are the catalogue's, one per declared status", () => {
    expect(ceilingStatusLabel("not_applicable")).toBe("Not applicable");
    expect(ceilingStatusLabel("within_ceiling")).toBe("Within ceiling");
    expect(ceilingStatusLabel("indeterminate")).toBe("Indeterminate");
    expect(ceilingStatusLabel("ceiling_reached")).toBe("Ceiling reached");
  });

  it("explain every status the registry declares, and say under of none of them", () => {
    expect(Object.keys(CEILING_STATUS_EXPLANATIONS).sort()).toEqual([...CEILING_STATUS_VALUES].sort());
    for (const sentence of Object.values(CEILING_STATUS_EXPLANATIONS)) {
      expect(sentence).not.toMatch(/\bunder\b/i);
    }
  });
});

describe("reading a ceiling assessment", () => {
  it("reads nothing evaluated as nothing evaluated, whatever the totals say", () => {
    // The wire nulls both figures here; a reading that carried them would be
    // inviting a renderer to write `?? 0`.
    expect(readCeiling(ceilingAssessment("not_applicable", { cost: incompleteTotal(5, 2) }))).toEqual({
      kind: "not_applicable",
    });
    expect(describeCeilingFigures({ kind: "not_applicable" }, "usd")).toBeNull();
  });

  // ⚠ #603 (ADR-0020 §7): under `indeterminate` the wire nulls both figures —
  // a cost still unresolved may move the total either way — and the reading
  // carries the nulls rather than inventing a share.
  it("carries the ceiling and the count the known total left out, and no figure UBB could not state", () => {
    const reading = readCeiling(
      ceilingAssessment("indeterminate", { ceiling_micros: 3_000_000, cost: incompleteTotal(1_240_000, 1) }),
    );
    expect(reading).toEqual({
      kind: "indeterminate",
      ceilingMicros: 3_000_000,
      usedPercentage: null,
      remainingMicros: null,
      eventsLeftOut: 1,
    });
  });
});

describe("the figures beside a ceiling status", () => {
  it("are figures where the status is a conclusion", () => {
    const within = readCeiling(
      ceilingAssessment("within_ceiling", { ceiling_micros: 3_000_000, cost: completeTotal(2_870_000) }),
    );
    expect(describeCeilingFigures(within, "usd")).toBe("$3.00 ceiling · 95% used · $0.13 headroom");

    const reached = readCeiling(
      ceilingAssessment("ceiling_reached", { ceiling_micros: 800_000, cost: completeTotal(900_000) }),
    );
    expect(describeCeilingFigures(reached, "usd")).toBe("$0.80 ceiling · 112% used · $0.00 headroom");
  });

  it("are the ceiling alone where UBB could not tell — no share, no headroom, and no bound", () => {
    const reading = readCeiling(
      ceilingAssessment("indeterminate", { ceiling_micros: 3_000_000, cost: incompleteTotal(1_240_000, 1) }),
    );
    expect(describeCeilingFigures(reading, "usd")).toBe("$3.00 ceiling");
  });

  // The owner's case (6279966961): a unit STOPPED at its ceiling on the known
  // total, with a cost still unresolved. Assembled here rather than read off a
  // mock, as the wire carries it: the stop is the enforcement trigger, and the
  // assessment beside it is indeterminate with no figures — never "reached".
  it("read a unit stopped on its known total while a cost is unresolved as indeterminate", () => {
    const reading = readCeiling({
      task_cogs_ceiling_micros: 800_000,
      ceiling_status: "indeterminate",
      ceiling_used_percentage: null,
      ceiling_remaining_micros: null,
      unresolved_event_count: 2,
    });
    expect(reading.kind).toBe("indeterminate");
    expect(describeCeilingFigures(reading, "usd")).toBe("$0.80 ceiling");
    expect(explainCeiling(reading)).toMatch(/fired on the costs already known and stands/);
    expect(explainCeiling(reading)).not.toMatch(/reached|at least|at most|higher|lower/i);
  });

  it("leave out a share of a zero ceiling rather than writing one", () => {
    // The wire sends `null` for the percentage of a zero ceiling (a share of
    // nothing is not a share) while still saying the ceiling is reached.
    const reading = readCeiling(
      ceilingAssessment("ceiling_reached", { ceiling_micros: 0, cost: completeTotal(0) }),
    );
    expect(describeCeilingFigures(reading, "usd")).toBe("$0.00 ceiling · $0.00 headroom");
  });

  it("are each readable on their own, for a surface that puts them in columns", () => {
    const within = readCeiling(
      ceilingAssessment("within_ceiling", { ceiling_micros: 3_000_000, cost: completeTotal(2_100_000) }),
    );
    expect(describeUtilisation(within)).toBe("70%");
    expect(describeHeadroom(within, "usd")).toBe("$0.90");

    const indeterminate = readCeiling(
      ceilingAssessment("indeterminate", { ceiling_micros: 3_000_000, cost: incompleteTotal(1_240_000, 1) }),
    );
    expect(describeUtilisation(indeterminate)).toBeNull();
    expect(describeHeadroom(indeterminate, "usd")).toBeNull();

    // Nothing evaluated: neither figure, and never a zero of either.
    expect(describeUtilisation({ kind: "not_applicable" })).toBeNull();
    expect(describeHeadroom({ kind: "not_applicable" }, "usd")).toBeNull();

    // A share of a zero ceiling is not a share; the clamped headroom is a
    // settled zero and renders as one.
    const zero = readCeiling(
      ceilingAssessment("ceiling_reached", { ceiling_micros: 0, cost: completeTotal(0) }),
    );
    expect(describeUtilisation(zero)).toBeNull();
    expect(describeHeadroom(zero, "usd")).toBe("$0.00");
  });

  it("leave out any figure the wire did not send, never writing zero for it", () => {
    // A shape the backend does not produce — an evaluated status with no pin
    // — but one the generated type admits, so the reader has to answer it.
    const reading = readCeiling({ ceiling_status: "within_ceiling", unresolved_event_count: 0 });
    expect(reading).toEqual({
      kind: "within_ceiling",
      ceilingMicros: null,
      usedPercentage: null,
      remainingMicros: null,
      eventsLeftOut: 0,
    });
    expect(describeCeilingFigures(reading, "usd")).toBeNull();
  });
});

describe("the sentence beside a ceiling status", () => {
  it("is the status's own where nothing was left out", () => {
    const within = readCeiling(
      ceilingAssessment("within_ceiling", { ceiling_micros: 10, cost: completeTotal(1) }),
    );
    expect(explainCeiling(within)).toBe(CEILING_STATUS_EXPLANATIONS.within_ceiling);
    expect(explainCeiling({ kind: "not_applicable" })).toBe(
      CEILING_STATUS_EXPLANATIONS.not_applicable,
    );
  });

  it("names how many events the known total left out, where that is what the status turns on", () => {
    const indeterminate = readCeiling(
      ceilingAssessment("indeterminate", { ceiling_micros: 10, cost: incompleteTotal(1, 1) }),
    );
    expect(explainCeiling(indeterminate)).toBe(
      `1 event has a supplier cost UBB has not learned. ${CEILING_STATUS_EXPLANATIONS.indeterminate}`,
    );

    // Reached is concluded only once every cost resolved, so it never has a
    // count to name.
    const reached = readCeiling(
      ceilingAssessment("ceiling_reached", { ceiling_micros: 10, cost: completeTotal(10) }),
    );
    expect(explainCeiling(reached)).toBe(CEILING_STATUS_EXPLANATIONS.ceiling_reached);
  });

  it("promises no direction in any sentence", () => {
    for (const sentence of Object.values(CEILING_STATUS_EXPLANATIONS)) {
      expect(sentence).not.toMatch(/at least|at most|can only|floor|softens/i);
    }
  });
});
