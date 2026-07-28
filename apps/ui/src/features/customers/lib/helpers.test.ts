import { describe, expect, it } from "vitest";

import { MOCK_MARGIN_ROWS } from "../api/mock-data";
import {
  filterMarginRows,
  listRowRevenueMicros,
  microsToUnits,
  parseAlertLevels,
  shortId,
  sortMarginRows,
  toMicros,
} from "./helpers";

describe("shortId", () => {
  it("shortens a UUID to its first segment", () => {
    expect(shortId("1f0c9c4e-8f2a-4a1e-9d3b-6a1f00000001")).toBe("1f0c9c4e…");
  });

  it("leaves non-dashed ids untouched", () => {
    expect(shortId("acme")).toBe("acme");
  });
});

describe("money conversion", () => {
  it("converts currency units to integer micros", () => {
    expect(toMicros("100")).toBe(100_000_000);
    expect(toMicros("0.35")).toBe(350_000);
  });

  it("round-trips micros back to units", () => {
    expect(microsToUnits(199_000_000)).toBe("199");
    expect(toMicros(microsToUnits(123_456_789))).toBe(123_456_789);
  });
});

describe("margin list sorting and filtering", () => {
  it("derives list-row revenue as subscription + usage revenue", () => {
    const acme = MOCK_MARGIN_ROWS[0]!;
    expect(listRowRevenueMicros(acme)).toBe(
      acme.subscription_revenue_micros + acme.usage_revenue_micros,
    );
  });

  it("sorts descending by the chosen measure", () => {
    const byRevenue = sortMarginRows(MOCK_MARGIN_ROWS, "revenue");
    const revenues = byRevenue.map(listRowRevenueMicros);
    expect(revenues).toEqual([...revenues].sort((a, b) => b - a));

    const byPct = sortMarginRows(MOCK_MARGIN_ROWS, "margin_pct");
    const pcts = byPct.map((row) => row.margin_percentage);
    expect(pcts).toEqual([...pcts].sort((a, b) => b - a));
  });

  it("filters on customer_id substring, case-insensitively", () => {
    const hits = filterMarginRows(MOCK_MARGIN_ROWS, "1F0C9C4E");
    expect(hits).toHaveLength(1);
    expect(filterMarginRows(MOCK_MARGIN_ROWS, "")).toHaveLength(
      MOCK_MARGIN_ROWS.length,
    );
    expect(filterMarginRows(MOCK_MARGIN_ROWS, "zzz")).toHaveLength(0);
  });
});

describe("parseAlertLevels", () => {
  it("parses comma-separated percentages and drops junk", () => {
    expect(parseAlertLevels("50, 80,100")).toEqual([50, 80, 100]);
    expect(parseAlertLevels("abc, 50, -2, ")).toEqual([50]);
    expect(parseAlertLevels("")).toEqual([]);
  });
});
