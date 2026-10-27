// A mirrored Stripe amount is drawn as it can honestly be shown (#564).
import { describe, expect, it } from "vitest";

import { mirroredAmount } from "./subscription-tab";

describe("mirroredAmount", () => {
  it("draws a dollar amount as money", () => {
    expect(mirroredAmount(199_000_000, "usd")).toMatch(/\$199(\.00)?/);
  });

  it("draws a quarantined amount as where the money is, never as a figure", () => {
    const shown = mirroredAmount(null, "eur");
    expect(shown).toBe("In EUR — left out of revenue (UBB accepts US dollars only)");
    expect(shown).not.toMatch(/[0-9]/);
  });

  it("says another currency where Stripe named none", () => {
    expect(mirroredAmount(null, "")).toContain("In another currency");
  });
});
