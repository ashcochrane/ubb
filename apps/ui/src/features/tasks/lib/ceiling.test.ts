// A run's ceiling assessment as the tasks feature reads and words it (#454).
//
// The page test (`run-detail-page.test.tsx`) renders each status from the
// mock; what is asserted here is the half a page cannot reach — the wire
// shapes the mock never authors, and the words the page composes from.

import { describe, expect, it } from "vitest";

import { ceilingAssessment, completeTotal, incompleteTotal } from "@/lib/economic-scenarios";
import { CEILING_STATUS_VALUES } from "@/lib/vocabulary";

import {
  CEILING_STATUS_EXPLANATIONS,
  ceilingStatusLabel,
  describeCeilingFigures,
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

  it("carries the three figures and the count the known total left out", () => {
    const reading = readCeiling(
      ceilingAssessment("indeterminate", { ceiling_micros: 3_000_000, cost: incompleteTotal(1_240_000, 1) }),
    );
    expect(reading).toEqual({
      kind: "indeterminate",
      ceilingMicros: 3_000_000,
      usedPercentage: 41,
      remainingMicros: 1_760_000,
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
      ceilingAssessment("ceiling_reached", { ceiling_micros: 800_000, cost: incompleteTotal(900_000, 2) }),
    );
    expect(describeCeilingFigures(reached, "usd")).toBe("$0.80 ceiling · 112% used · $0.00 headroom");
  });

  it("are a floor and a most where UBB could not tell", () => {
    const reading = readCeiling(
      ceilingAssessment("indeterminate", { ceiling_micros: 3_000_000, cost: incompleteTotal(1_240_000, 1) }),
    );
    expect(describeCeilingFigures(reading, "usd")).toBe(
      "$3.00 ceiling · at least 41% used · at most $1.76 headroom",
    );
  });

  it("leave out a share of a zero ceiling rather than writing one", () => {
    // The wire sends `null` for the percentage of a zero ceiling (a share of
    // nothing is not a share) while still saying the ceiling is reached.
    const reading = readCeiling(
      ceilingAssessment("ceiling_reached", { ceiling_micros: 0, cost: completeTotal(0) }),
    );
    expect(describeCeilingFigures(reading, "usd")).toBe("$0.00 ceiling · $0.00 headroom");
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

    const reached = readCeiling(
      ceilingAssessment("ceiling_reached", { ceiling_micros: 10, cost: incompleteTotal(10, 3) }),
    );
    expect(explainCeiling(reached)).toBe(
      `3 events have a supplier cost UBB has not learned. ${CEILING_STATUS_EXPLANATIONS.ceiling_reached}`,
    );
  });
});
