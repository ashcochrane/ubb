// The events mock's two grains of one clock (#510).
//
// The receipt reads one posting's `measurements_status`; the analytics answers
// publish `measurement_data_available_from`. They are two facts about ONE
// clock, and until #510 this mock told them apart: its answers said
// measurements were held from 2026-01-01 while its pruned seed is dated in
// May. A grouping by what was measured reads the seeds' own bags, so the two
// have to agree for that grouping to answer what a server would — which is
// what these cases hold, in both directions.

import { describe, expect, it } from "vitest";

import { ALL_EVENTS, MEASUREMENT_HORIZON } from "./mock-data";

/** The seeds that were metered — a charge posting was never measured, so no
 *  horizon governs its empty bag. */
const METERED = ALL_EVENTS.filter((event) => event.detail.kind !== "task_charge");

const before = (event: (typeof ALL_EVENTS)[number]) =>
  event.detail.effective_at.slice(0, 10) < MEASUREMENT_HORIZON;

describe("the measurement horizon and the seeds it governs", () => {
  // The vacuity floor: a horizon no seed precedes would make the first case
  // below pass by having nothing to check.
  it("has metered seeds on both sides of the horizon", () => {
    expect(METERED.filter(before).length).toBeGreaterThan(0);
    expect(METERED.filter((event) => !before(event)).length).toBeGreaterThan(0);
  });

  it("composes every metered seed older than the horizon as pruned", () => {
    for (const event of METERED.filter(before)) {
      expect(event.detail.measurements_status, event.detail.id).toBe("pruned");
      expect(event.detail.measurements, event.detail.id).toEqual({});
    }
  });

  it("composes no seed on or after the horizon as pruned", () => {
    for (const event of METERED.filter((seed) => !before(seed))) {
      expect(event.detail.measurements_status, event.detail.id).not.toBe("pruned");
    }
  });
});
