import { describe, expect, it } from "vitest";

import {
  createPlanSchema,
  currencyToMicros,
  editPlanSchema,
  toPlanIn,
  toPlanUpdateIn,
} from "./plan-form";

describe("currencyToMicros", () => {
  it("converts currency units to integer micros", () => {
    expect(currencyToMicros("29")).toBe(29_000_000);
    expect(currencyToMicros("29.50")).toBe(29_500_000);
    expect(currencyToMicros("0.000001")).toBe(1);
    expect(currencyToMicros("0")).toBe(0);
  });
});

describe("createPlanSchema", () => {
  const valid = {
    key: "team-monthly",
    name: "Team",
    accessFee: "99",
    perSeatFee: "",
    intervalChoice: "month" as const,
    customInterval: "",
  };

  it("accepts a valid plan and converts to PlanIn", () => {
    const parsed = createPlanSchema.parse(valid);
    expect(toPlanIn(parsed)).toEqual({
      key: "team-monthly",
      name: "Team",
      access_fee_micros: 99_000_000,
      per_seat_micros: 0,
      interval: "month",
    });
  });

  it("rejects keys over 64 characters", () => {
    const result = createPlanSchema.safeParse({ ...valid, key: "k".repeat(65) });
    expect(result.success).toBe(false);
  });

  it("rejects negative or non-numeric money input", () => {
    expect(createPlanSchema.safeParse({ ...valid, accessFee: "-5" }).success).toBe(false);
    expect(createPlanSchema.safeParse({ ...valid, accessFee: "abc" }).success).toBe(false);
  });

  it("requires the custom interval text when the choice is custom", () => {
    const result = createPlanSchema.safeParse({
      ...valid,
      intervalChoice: "custom" as const,
      customInterval: "",
    });
    expect(result.success).toBe(false);

    const ok = createPlanSchema.parse({
      ...valid,
      intervalChoice: "custom" as const,
      customInterval: "week",
    });
    expect(toPlanIn(ok).interval).toBe("week");
  });
});

describe("editPlanSchema", () => {
  it("requires at least one fee to change", () => {
    const result = editPlanSchema.safeParse({
      key: "team-monthly",
      accessFee: "",
      perSeatFee: "",
      migrateExisting: false,
    });
    expect(result.success).toBe(false);
  });

  it("maps blank fees to null (leave unchanged) in PlanUpdateIn", () => {
    const parsed = editPlanSchema.parse({
      key: "team-monthly",
      accessFee: "129.50",
      perSeatFee: "",
      migrateExisting: true,
    });
    expect(toPlanUpdateIn(parsed)).toEqual({
      access_fee_micros: 129_500_000,
      per_seat_micros: null,
      migrate_existing: true,
    });
  });
});
