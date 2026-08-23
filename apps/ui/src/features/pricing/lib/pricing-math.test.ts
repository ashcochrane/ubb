import { describe, expect, it } from "vitest";

import {
  exampleChargeMicros,
  microsToUnitString,
  toMicros,
  unitChoiceFor,
  unitQuantityLabel,
  type RuleArithmetic,
} from "./pricing-math";
import { resolveUnitQuantity, ruleFormSchema, statedGroupingFields } from "./schemas";

describe("toMicros", () => {
  it("converts currency units to integer micros without float drift", () => {
    expect(toMicros("2.5")).toBe(2_500_000);
    expect(toMicros("19.99")).toBe(19_990_000);
    expect(toMicros("0.000001")).toBe(1);
    // 0.1 + 0.2 = 0.30000000000000004 in IEEE-754; rounding is what saves it.
    expect(toMicros(0.1 + 0.2)).toBe(300_000);
  });

  it("round-trips through microsToUnitString", () => {
    expect(toMicros(microsToUnitString(2_500_000))).toBe(2_500_000);
    expect(microsToUnitString(15_000_000)).toBe("15");
  });
});

describe("exampleChargeMicros", () => {
  it("prices per unit against the rule's own denominator", () => {
    const rule: RuleArithmetic = {
      rate_structure: "per_unit",
      rate_per_unit_micros: 2_500_000,
      unit_quantity: 1_000_000,
      fixed_micros: 0,
    };

    expect(exampleChargeMicros(rule, 1_000_000)).toBe(2_500_000);
    expect(exampleChargeMicros(rule, 400_000)).toBe(1_000_000);
  });

  it("adds the flat component on top of a per-unit charge", () => {
    expect(
      exampleChargeMicros(
        {
          rate_structure: "per_unit",
          rate_per_unit_micros: 1_000_000,
          unit_quantity: 1_000,
          fixed_micros: 50_000,
        },
        2_000,
      ),
    ).toBe(2_050_000);
  });

  it("charges only the fixed component when that is the arithmetic", () => {
    // ⚠ THE UNITS ARE IGNORED, WHICH IS WHAT THE SHAPE MEANS. A fixed
    // component applies once regardless of quantity, so a rule moving between
    // the two shapes changes what a tenant is charged even where neither money
    // term moved — the reason the diff renders the shape beside the amount.
    expect(
      exampleChargeMicros(
        {
          rate_structure: "fixed_component",
          rate_per_unit_micros: 9_999_999,
          unit_quantity: 1,
          fixed_micros: 40_000,
        },
        5_000,
      ),
    ).toBe(40_000);
  });
});

describe("unit quantity choices", () => {
  it("maps a stored denominator to its choice, and names it", () => {
    expect(unitChoiceFor(1)).toBe("1");
    expect(unitChoiceFor(1_000)).toBe("1000");
    expect(unitChoiceFor(1_000_000)).toBe("1000000");
    expect(unitChoiceFor(500)).toBe("custom");
    expect(unitQuantityLabel(1_000_000)).toBe("per 1M units");
    expect(unitQuantityLabel(500)).toBe("per 500 units");
  });
});

describe("the rule form", () => {
  const base = {
    measurement_key: "gpt4o_input_tokens",
    provider: "openai",
    event_type: "chat.completion",
    task_type: "",
    subtask_type: "",
    grouping_fields: {},
    pricing_method: "direct_event_price" as const,
    rate_structure: "per_unit" as const,
    rate: "2.5",
    unit_choice: "1000000" as const,
    custom_unit: "",
    fixed: "0",
  };

  it("accepts a whole rule and resolves its denominator", () => {
    expect(ruleFormSchema.safeParse(base).success).toBe(true);
    expect(resolveUnitQuantity({ unit_choice: "1000000", custom_unit: "" })).toBe(
      1_000_000,
    );
  });

  it("refuses a custom denominator that is not a whole number of units", () => {
    expect(
      ruleFormSchema.safeParse({ ...base, unit_choice: "custom", custom_unit: "2.5" })
        .success,
    ).toBe(false);
    expect(
      ruleFormSchema.safeParse({ ...base, unit_choice: "custom", custom_unit: "500" })
        .success,
    ).toBe(true);
    expect(resolveUnitQuantity({ unit_choice: "custom", custom_unit: "500" })).toBe(500);
  });

  it("refuses a negative amount", () => {
    const result = ruleFormSchema.safeParse({ ...base, rate: "-1" });
    expect(result.success).toBe(false);
  });

  // ⚠ THE METHOD IS PART OF THE RULE, WHICH IS THE CONSOLE OBLIGATION SPEC §21
  // SAYS IS USUALLY MISSED. A schema that validated an amount and let the
  // method ride along untouched would be a form that cannot express moving a
  // customer from a margin over cost onto a flat price — the change that
  // alters the shape of a negotiated deal rather than its number.
  it("refuses a method the registry does not declare", () => {
    expect(
      ruleFormSchema.safeParse({ ...base, pricing_method: "cost_plus_vat" }).success,
    ).toBe(false);
    expect(
      ruleFormSchema.safeParse({ ...base, pricing_method: "margin_over_cost" }).success,
    ).toBe(true);
  });

  // ⚠ AN UNPINNED SELECTOR IS "" EVERYWHERE ON THIS SURFACE, so a slot the
  // tenant left blank must not reach the body as a pin on the empty string —
  // that would be a rule matching only events whose grouping value is
  // literally empty, which is not what an empty box means.
  it("drops the slots a tenant left blank", () => {
    expect(
      statedGroupingFields({ model: "gpt-4o", region: "", tier: "  " }),
    ).toEqual({ model: "gpt-4o" });
  });
});
