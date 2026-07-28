import { describe, expect, it } from "vitest";

import type { PostpaidConfig } from "../api/types";
import { toRevenueDailyRow } from "../api/types";
import {
  budgetFormToPayload,
  budgetToFormValues,
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
    // The budget PUT is a full upsert: a lossy prefill would silently
    // rewrite sub-cent micros on save (2_500_500 → "2.50" → 2_500_000).
    expect(microsToCurrencyInput(2_500_500)).toBe("2.5005");
    for (const micros of [2_500_500, 182_500_000, 999_999_999_999, 1, 10_000]) {
      expect(currencyToMicros(microsToCurrencyInput(micros))).toBe(micros);
    }
  });
});

describe("budget form (full upsert)", () => {
  it("round-trips the GET payload and always submits every field", () => {
    const values = budgetToFormValues({
      cap_micros: 2_500_000_000,
      enforce_mode: "advisory",
      hard_stop_pct: 120,
      alert_levels: [80, 50, 100],
      fail_closed: false,
    });
    expect(values.cap).toBe("2500");
    expect(values.alert_levels).toEqual([50, 80, 100]); // sorted for display

    const payload = budgetFormToPayload(values);
    // A full upsert: every field present, even ones the user never touched.
    expect(payload).toEqual({
      cap_micros: 2_500_000_000,
      enforce_mode: "advisory",
      hard_stop_pct: 120,
      alert_levels: [50, 80, 100],
      fail_closed: false,
    });
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

describe("untyped revenue daily rows", () => {
  it("narrows backend rows and degrades bad data to zeros", () => {
    expect(
      toRevenueDailyRow({
        day: "2026-07-01",
        provider_cost_micros: 10,
        billed_cost_micros: 13,
        event_count: 2,
      }),
    ).toEqual({
      day: "2026-07-01",
      provider_cost_micros: 10,
      billed_cost_micros: 13,
      event_count: 2,
    });
    expect(toRevenueDailyRow({ day: 42, provider_cost_micros: "x" })).toEqual({
      day: "",
      provider_cost_micros: 0,
      billed_cost_micros: 0,
      event_count: 0,
    });
  });
});

describe("month filter", () => {
  it("maps the month input to the API's period-start date", () => {
    expect(monthToPeriodDate("2026-07")).toBe("2026-07-01");
    expect(monthToPeriodDate("")).toBeUndefined();
    expect(monthToPeriodDate("garbage")).toBeUndefined();
  });
});
