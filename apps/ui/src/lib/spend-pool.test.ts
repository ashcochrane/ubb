// The pool's words and readers (#468; slice 6 §4, §18). The expected words
// are SPELLED here rather than asked of the binding, so a binding pointed at
// the wrong concept's keys — or a catalogue entry that drifts — goes red.

import { describe, expect, it } from "vitest";

import { SPEND_POOL_ENFORCE_MODE_VALUES } from "@/lib/vocabulary";

import {
  describePoolHeadroom,
  describePoolUtilisation,
  excludedFromKnown,
  POOL_LEVEL,
  POOL_POSTURE,
  poolLevel,
  readPoolCharges,
  SPEND_POOL_ENFORCE_MODE_WORDS,
  spendPoolEnforceModeLabel,
  type CustomerSpendPoolStatus,
} from "./spend-pool";

/** A pool's status pair as the wire carries it, every field required. */
function status(overrides: Partial<CustomerSpendPoolStatus>): CustomerSpendPoolStatus {
  return {
    period: "2026-07",
    cap_micros: 500_000_000,
    enforce_mode: "alert_only",
    known_period_charges_micros: 231_400_000,
    unresolved_posting_count: 0,
    used_percentage: 46,
    remaining_micros: 268_600_000,
    highest_threshold_reached: null,
    blocking_occurred: false,
    ...overrides,
  };
}

describe("the enforce mode's words", () => {
  it("binds the catalogue's wording for each of the registry's two modes", () => {
    expect(spendPoolEnforceModeLabel("alert_only")).toBe("Alert only");
    expect(spendPoolEnforceModeLabel("blocking")).toBe("Blocking");
  });

  it("offers a form every mode the registry declares, worded, in the registry's order", () => {
    expect(Object.keys(SPEND_POOL_ENFORCE_MODE_WORDS)).toEqual([...SPEND_POOL_ENFORCE_MODE_VALUES]);
    expect(SPEND_POOL_ENFORCE_MODE_WORDS).toEqual({ alert_only: "Alert only", blocking: "Blocking" });
  });

  it("has a posture sentence for every mode, and none says the mode's name alone", () => {
    for (const mode of SPEND_POOL_ENFORCE_MODE_VALUES) {
      expect(POOL_POSTURE[mode].length).toBeGreaterThan(20);
    }
    expect(POOL_POSTURE.alert_only).toMatch(/never stops/);
    expect(POOL_POSTURE.blocking).toMatch(/refused/);
  });
});

describe("the pool's status pair", () => {
  it("reads the known charges as a figure where every posting is priced", () => {
    expect(readPoolCharges(status({}))).toEqual({ kind: "figure", micros: 231_400_000 });
    expect(excludedFromKnown(status({}))).toBeNull();
  });

  it("reads the known charges as a floor beside the count it excludes, never as a figure", () => {
    const pool = status({ known_period_charges_micros: 517_500_000, unresolved_posting_count: 1 });
    expect(readPoolCharges(pool)).toEqual({ kind: "floor", micros: 517_500_000, eventsLeftOut: 1 });
    expect(excludedFromKnown(pool)).toBe(
      "1 posting whose revenue UBB has not resolved is excluded from the known figure, not counted as zero.",
    );
    expect(
      excludedFromKnown(status({ known_period_charges_micros: 1, unresolved_posting_count: 3 })),
    ).toBe(
      "3 postings whose revenue UBB has not resolved are excluded from the known figure, not counted as zero.",
    );
  });

  it("reads a known figure of nothing beside an unresolved posting as unknown, never as zero", () => {
    const pool = status({ known_period_charges_micros: 0, unresolved_posting_count: 2 });
    expect(readPoolCharges(pool)).toEqual({ kind: "unknown", eventsLeftOut: 2 });
  });

  it("says the share used is at least where the pair is a floor, and a figure otherwise", () => {
    expect(describePoolUtilisation(status({}))).toBe("46%");
    expect(describePoolUtilisation(status({ unresolved_posting_count: 2 }))).toBe("at least 46%");
    expect(describePoolUtilisation(status({ used_percentage: null }))).toBeNull();
  });

  it("says the headroom is at most where the pair is a floor, except a clamped zero", () => {
    expect(describePoolHeadroom(status({}), "usd")).toBe("$268.60");
    expect(describePoolHeadroom(status({ unresolved_posting_count: 2 }), "usd")).toBe("at most $268.60");
    // Past the line the kernel clamps the headroom at nothing, and a posting
    // it could not price can only lower a figure already at its floor.
    expect(
      describePoolHeadroom(status({ remaining_micros: 0, unresolved_posting_count: 1 }), "usd"),
    ).toBe("$0.00");
    expect(describePoolHeadroom(status({ remaining_micros: null }), "usd")).toBeNull();
  });
});

describe("the level a pool applies at, in words", () => {
  it("is this customer's own where a pool is declared on them", () => {
    expect(poolLevel({ cap_micros: 500_000_000 }, status({}))).toBe("declared_here");
    expect(POOL_LEVEL.declared_here).toMatch(/^Declared on this customer/);
  });

  it("is the workspace default for seats where none is declared here and one still applies", () => {
    expect(poolLevel({ cap_micros: 0 }, status({ cap_micros: 2_500_000_000 }))).toBe("seat_default");
    expect(POOL_LEVEL.seat_default).toMatch(/workspace default for seats applies/);
  });

  it("is no pool at all where none is declared here and none reaches them", () => {
    expect(poolLevel({ cap_micros: 0 }, status({ cap_micros: 0 }))).toBe("none");
    expect(POOL_LEVEL.none).toMatch(/^No pool applies to this customer/);
    expect(POOL_LEVEL.none).toMatch(/reaches seats only/);
  });
});
