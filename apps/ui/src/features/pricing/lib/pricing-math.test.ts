import { describe, expect, it } from "vitest";

import {
  exampleChargeMicros,
  microsToUnitString,
  sameRateValues,
  toMicros,
  unitChoiceFor,
  unitQuantityLabel,
} from "./pricing-math";
import { markupFormSchema, rateFormSchema, resolveUnitQuantity } from "./schemas";

describe("toMicros", () => {
  it("converts currency-unit input to integer micros with rounding", () => {
    expect(toMicros("2.5")).toBe(2_500_000);
    expect(toMicros("19.99")).toBe(19_990_000);
    expect(toMicros("0.000001")).toBe(1);
    // Float noise is rounded away — money stays integral.
    expect(toMicros(0.1 + 0.2)).toBe(300_000);
  });

  it("round-trips through microsToUnitString", () => {
    expect(toMicros(microsToUnitString(2_500_000))).toBe(2_500_000);
    expect(microsToUnitString(15_000_000)).toBe("15");
  });
});

describe("exampleChargeMicros", () => {
  it("computes a per-unit charge with integer math", () => {
    // $2.50 per 1M units → 1,000 units = 2,500 micros ($0.0025).
    const charge = exampleChargeMicros(
      {
        pricing_model: "per_unit",
        rate_per_unit_micros: 2_500_000,
        unit_quantity: 1_000_000,
        fixed_micros: 0,
      },
      1_000,
    );
    expect(charge).toBe(2_500);
  });

  it("floors fractional micros and adds the fixed component", () => {
    const charge = exampleChargeMicros(
      {
        pricing_model: "per_unit",
        rate_per_unit_micros: 1,
        unit_quantity: 3,
        fixed_micros: 10,
      },
      1_000,
    );
    expect(charge).toBe(Math.floor(1_000 / 3) + 10);
  });

  it("charges only the fixed amount for flat rates", () => {
    const charge = exampleChargeMicros(
      {
        pricing_model: "flat",
        rate_per_unit_micros: 999,
        unit_quantity: 1_000,
        fixed_micros: 40_000,
      },
      1_000_000,
    );
    expect(charge).toBe(40_000);
  });
});

describe("unit quantity helpers", () => {
  it("maps standard quantities to select choices and labels", () => {
    expect(unitChoiceFor(1)).toBe("1");
    expect(unitChoiceFor(1_000)).toBe("1000");
    expect(unitChoiceFor(1_000_000)).toBe("1000000");
    expect(unitChoiceFor(500)).toBe("custom");
    expect(unitQuantityLabel(1_000_000)).toBe("per 1M units");
    expect(unitQuantityLabel(500)).toBe("per 500 units");
  });

  it("detects identical and differing rate values (publish diffing)", () => {
    const base = {
      pricing_model: "per_unit",
      rate_per_unit_micros: 2_500_000,
      unit_quantity: 1_000_000,
      fixed_micros: 0,
    };
    expect(sameRateValues(base, { ...base })).toBe(true);
    expect(sameRateValues(base, { ...base, rate_per_unit_micros: 3_000_000 })).toBe(false);
  });
});

describe("form schemas", () => {
  it("rejects non-numeric and negative markup input", () => {
    expect(markupFormSchema.safeParse({ percent: "abc", fixed: "0" }).success).toBe(false);
    expect(markupFormSchema.safeParse({ percent: "-5", fixed: "0" }).success).toBe(false);
    expect(markupFormSchema.safeParse({ percent: "15", fixed: "0.05" }).success).toBe(true);
  });

  it("requires a positive whole number for custom unit quantities", () => {
    const base = {
      metric_name: "gpt4o_input_tokens",
      provider: "openai",
      event_type: "",
      task_type: "",
      pricing_model: "per_unit",
      rate: "2.5",
      unit_choice: "custom",
      fixed: "0",
    } as const;
    expect(rateFormSchema.safeParse({ ...base, custom_unit: "2.5" }).success).toBe(false);
    expect(rateFormSchema.safeParse({ ...base, custom_unit: "500" }).success).toBe(true);
    expect(resolveUnitQuantity({ unit_choice: "custom", custom_unit: "500" })).toBe(500);
    expect(resolveUnitQuantity({ unit_choice: "1000000", custom_unit: "" })).toBe(1_000_000);
  });

  it("requires a metric name", () => {
    const result = rateFormSchema.safeParse({
      metric_name: "",
      provider: "",
      event_type: "",
      task_type: "",
      pricing_model: "flat",
      rate: "0",
      unit_choice: "1",
      custom_unit: "",
      fixed: "0.04",
    });
    expect(result.success).toBe(false);
  });
});
