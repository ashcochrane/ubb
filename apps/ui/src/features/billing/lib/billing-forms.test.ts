import { describe, expect, it } from "vitest";

import type { PostpaidConfig } from "../api/types";
import {
  buildPostpaidPayload,
  currencyToMicros,
  microsToCurrencyInput,
  monthToPeriodDate,
} from "./billing-forms";

describe("currency conversion", () => {
  it("converts currency-unit input to integer micros and back", () => {
    expect(currencyToMicros("25")).toBe(25_000_000);
    expect(currencyToMicros("0.01")).toBe(10_000);
    expect(currencyToMicros("2500.5")).toBe(2_500_500_000);
    expect(currencyToMicros("not a number")).toBeNaN();
    expect(microsToCurrencyInput(2_500_000_000)).toBe("2500");
    expect(microsToCurrencyInput(182_500_000)).toBe("182.5");
  });

  it("prefills at full precision so an untouched save round-trips identical micros", () => {
    // The pool PUT is a full upsert: a lossy prefill would silently
    // rewrite sub-cent micros on save (2_500_500 → "2.50" → 2_500_000).
    expect(microsToCurrencyInput(2_500_500)).toBe("2.5005");
    for (const micros of [2_500_500, 182_500_000, 999_999_999_999, 1, 10_000]) {
      expect(currencyToMicros(microsToCurrencyInput(micros))).toBe(micros);
    }
  });
});

describe("postpaid partial-update payload", () => {
  const current: PostpaidConfig = {
    usage_line_item_group_by: "product_id",
    consolidate_with_subscription: false,
  };

  it("omits unchanged fields entirely", () => {
    expect(
      buildPostpaidPayload(current, { mode: "product", tagKey: "", consolidate: true }),
    ).toEqual({ consolidate_with_subscription: true });
  });

  it("sends an explicit empty string to clear grouping", () => {
    expect(
      buildPostpaidPayload(current, { mode: "single", tagKey: "", consolidate: false }),
    ).toEqual({ usage_line_item_group_by: "" });
  });

  it("builds tag:<key> values and returns null when nothing changed", () => {
    expect(
      buildPostpaidPayload(current, { mode: "tag", tagKey: "seat", consolidate: false }),
    ).toEqual({ usage_line_item_group_by: "tag:seat" });
    expect(
      buildPostpaidPayload(current, { mode: "product", tagKey: "", consolidate: false }),
    ).toBeNull();
  });
});

// ⚠ THE UNTYPED-ROW SUITE IS GONE WITH THE SHAPE IT NARROWED (#501). Two
// cases asserted that a day row was read off an `additionalProperties: true`
// body and that bad data degraded to zeros rather than crashing the chart — a
// narrowing that existed because the revenue report left its day rows untyped.
//
// The one economic query DECLARES its row, so the day series arrives typed: a
// key that moved is a contract break the drift and breaking gates see, not a
// silent zero this console has to defend against. What replaced the narrowing
// is `toRevenueWindow` in `../api/types`, tested through the mock it serves.

describe("month filter", () => {
  it("maps the month input to the API's period-start date", () => {
    expect(monthToPeriodDate("2026-07")).toBe("2026-07-01");
    expect(monthToPeriodDate("")).toBeUndefined();
    expect(monthToPeriodDate("garbage")).toBeUndefined();
  });
});
