import { describe, expect, it } from "vitest";

import type { PostpaidConfig } from "../api/types";
import {
  buildPostpaidPayload,
  currencyToMicros,
  microsToCurrencyInput,
  monthToPeriodDate,
  postpaidToFormState,
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
  // ⚠ **THE STORED VALUE IS ONE REQUEST WORD OF THE GROUPING VOCABULARY NOW
  // (#503), NOT A MODE PLUS A FREE-TEXT KEY.** What this form used to build —
  // `single`, `product_id`, `tag:<anything the tenant typed>` — is what
  // ADR-0005 calls the sharpest of the three free-text hatches, and it is the
  // only one a paying customer reads: an unbounded key driving invoice line
  // labels is how a 5,000-line invoice happens. The server now refuses a word
  // with no kind, so `product_id` is not merely renamed here, it is a value
  // the API would reject.
  const current: PostpaidConfig = {
    group_by: "field:event_type",
    consolidate_with_subscription: false,
  };

  it("omits unchanged fields entirely", () => {
    expect(
      buildPostpaidPayload(current, { axis: "field:event_type", consolidate: true }),
    ).toEqual({ consolidate_with_subscription: true });
  });

  it("sends an explicit empty string to clear grouping", () => {
    // One total, one line — the absence of an axis rather than an axis meaning
    // "don't". The PUT is partial, so clearing has to be said explicitly.
    expect(
      buildPostpaidPayload(current, { axis: "", consolidate: false }),
    ).toEqual({ group_by: "" });
  });

  it("sends the axis's own request word, kind included", () => {
    expect(
      buildPostpaidPayload(current, { axis: "rollup:event_category", consolidate: false }),
    ).toEqual({ group_by: "rollup:event_category" });
    expect(
      buildPostpaidPayload(current, { axis: "field:event_type", consolidate: false }),
    ).toBeNull();
  });

  it("reads the stored axis back as the form's own state", () => {
    expect(postpaidToFormState(current)).toEqual({
      axis: "field:event_type",
      consolidate: false,
    });
    expect(
      postpaidToFormState({ ...current, group_by: "" }),
    ).toEqual({ axis: "", consolidate: false });
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
