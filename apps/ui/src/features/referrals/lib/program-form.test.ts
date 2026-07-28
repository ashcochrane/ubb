import { describe, expect, it } from "vitest";

import {
  emptyProgramFormValues,
  programFormSchema,
  programToFormValues,
  toProgramCreateRequest,
  toProgramUpdateRequest,
  type ProgramFormValues,
} from "./program-form";
import {
  attributeFormSchema,
  toAttributeRequest,
  type AttributeFormValues,
} from "./schemas";

function values(overrides: Partial<ProgramFormValues>): ProgramFormValues {
  return { ...emptyProgramFormValues(), reward_amount: "10", ...overrides };
}

describe("programFormSchema (create-time bounds, applied to edit too)", () => {
  it("accepts a valid revenue share program", () => {
    expect(programFormSchema.safeParse(values({})).success).toBe(true);
  });

  it("rejects a share percentage over 100", () => {
    const result = programFormSchema.safeParse(values({ reward_amount: "150" }));
    expect(result.success).toBe(false);
  });

  it("accepts a flat fee over 100 currency units (micros scale, not percent)", () => {
    const result = programFormSchema.safeParse(
      values({ reward_type: "flat_fee", reward_amount: "150" }),
    );
    expect(result.success).toBe(true);
  });

  it("bounds the attribution window to 1–365", () => {
    expect(
      programFormSchema.safeParse(values({ attribution_window_days: "0" })).success,
    ).toBe(false);
    expect(
      programFormSchema.safeParse(values({ attribution_window_days: "400" })).success,
    ).toBe(false);
    expect(
      programFormSchema.safeParse(values({ attribution_window_days: "365" })).success,
    ).toBe(true);
  });

  it("bounds the fraud limits", () => {
    expect(
      programFormSchema.safeParse(values({ max_referrals_per_day: "20000" })).success,
    ).toBe(false);
    expect(
      programFormSchema.safeParse(values({ min_customer_age_hours: "9000" })).success,
    ).toBe(false);
    expect(programFormSchema.safeParse(values({ min_customer_age_hours: "0" })).success).toBe(
      true,
    );
  });
});

describe("program request converters", () => {
  it("converts a flat fee entered in currency units to integer micros", () => {
    const body = toProgramCreateRequest(
      values({ reward_type: "flat_fee", reward_amount: "5.5" }),
    );
    expect(body.reward_type).toBe("flat_fee");
    expect(body.reward_value).toBe(5_500_000);
  });

  it("keeps share percentages as-is and nulls cleared optionals", () => {
    const body = toProgramUpdateRequest(values({ reward_amount: "12.5" }));
    expect(body.reward_value).toBe(12.5);
    expect(body.reward_window_days).toBeNull();
    expect(body.max_reward_micros).toBeNull();
    expect(body.max_referrals_per_day).toBeNull();
  });

  it("converts the lifetime cap to micros", () => {
    const body = toProgramCreateRequest(values({ max_reward: "500" }));
    expect(body.max_reward_micros).toBe(500_000_000);
  });

  it("round-trips a program into form values (flat fee micros → currency units)", () => {
    const form = programToFormValues({
      id: "prog-1",
      reward_type: "flat_fee",
      reward_value: 5_000_000,
      attribution_window_days: 30,
      reward_window_days: null,
      max_reward_micros: 250_000_000,
      estimated_cost_percentage: null,
      max_referrals_per_day: 50,
      min_customer_age_hours: null,
      status: "active",
      created_at: "2026-03-02T09:15:00Z",
      updated_at: "2026-06-15T14:40:00Z",
    });
    expect(form.reward_amount).toBe("5");
    expect(form.max_reward).toBe("250");
    expect(form.reward_window_days).toBe("");
    expect(form.max_referrals_per_day).toBe("50");
  });
});

describe("attribute form (exactly one of code | link_token)", () => {
  const base: AttributeFormValues = {
    customer_id: "a1b2c3d4-9f10-4e8b-b2aa-101010101001",
    method: "code",
    code: "REF-ACME8821",
    link_token: "rlt_should_never_be_sent",
  };

  it("sends ONLY the code when attributing by code", () => {
    const body = toAttributeRequest(base);
    expect(body.code).toBe("REF-ACME8821");
    expect(body.link_token).toBeNull();
  });

  it("sends ONLY the link token when attributing by link", () => {
    const body = toAttributeRequest({ ...base, method: "link_token" });
    expect(body.code).toBeNull();
    expect(body.link_token).toBe("rlt_should_never_be_sent");
  });

  it("requires the field matching the chosen method", () => {
    expect(attributeFormSchema.safeParse({ ...base, code: "" }).success).toBe(false);
    expect(
      attributeFormSchema.safeParse({ ...base, method: "link_token", link_token: "" }).success,
    ).toBe(false);
  });

  it("rejects a non-UUID referred customer id", () => {
    expect(
      attributeFormSchema.safeParse({ ...base, customer_id: "acct-golden-fox" }).success,
    ).toBe(false);
  });
});
