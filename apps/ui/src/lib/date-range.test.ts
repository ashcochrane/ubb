import { describe, expect, it } from "vitest";

import { datetimeWindow } from "./date-range";

// Moved here from the events feature in #466, with the helper: two surfaces
// hand the same window to Stops and breaches.
describe("datetimeWindow", () => {
  it("maps inclusive calendar dates onto a half-open datetime window", () => {
    expect(datetimeWindow({ start_date: "2026-07-01", end_date: "2026-07-23" })).toEqual({
      since: "2026-07-01T00:00:00Z",
      until: "2026-07-24T00:00:00Z",
    });
  });

  it("rolls the until date across month boundaries", () => {
    expect(datetimeWindow({ start_date: "2026-07-01", end_date: "2026-07-31" }).until).toBe(
      "2026-08-01T00:00:00Z",
    );
  });
});
