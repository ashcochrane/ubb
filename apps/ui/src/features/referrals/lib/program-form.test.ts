import { describe, expect, it } from "vitest";

import {
  basisPointsPercentLabel,
  emptyProgramFormValues,
  programFormSchema,
  programToFormValues,
  rewardSummary,
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

  // A-3: the wire takes basis points 1..10000, so the percent entry is
  // 0.01..100 to two decimal places — 100.01 % is a basis point past the
  // whole, and 0.001 % is finer than one basis point.
  it("refuses a share past the whole or finer than one basis point", () => {
    expect(programFormSchema.safeParse(values({ reward_amount: "100.01" })).success).toBe(false);
    expect(programFormSchema.safeParse(values({ reward_amount: "0.001" })).success).toBe(false);
    expect(programFormSchema.safeParse(values({ reward_amount: "0" })).success).toBe(false);
    expect(programFormSchema.safeParse(values({ reward_amount: "100" })).success).toBe(true);
    expect(programFormSchema.safeParse(values({ reward_amount: "0.01" })).success).toBe(true);
    expect(programFormSchema.safeParse(values({ reward_amount: "12.5" })).success).toBe(true);
  });

  it("accepts a flat fee over 100 currency units (micros scale, not percent)", () => {
    const result = programFormSchema.safeParse(
      values({ reward_type: "flat_fee", reward_amount: "150" }),
    );
    expect(result.success).toBe(true);
  });

  it("bounds the estimated cost to 0–100 % in whole basis points", () => {
    expect(programFormSchema.safeParse(values({ estimated_cost_percent: "100" })).success).toBe(true);
    expect(programFormSchema.safeParse(values({ estimated_cost_percent: "0" })).success).toBe(true);
    expect(programFormSchema.safeParse(values({ estimated_cost_percent: "100.01" })).success).toBe(false);
    expect(programFormSchema.safeParse(values({ estimated_cost_percent: "-1" })).success).toBe(false);
    expect(programFormSchema.safeParse(values({ estimated_cost_percent: "5.005" })).success).toBe(false);
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

// A-3: exactly one reward figure goes out, the one the type names — micros
// for a flat fee, basis points for a share — and the other key is not sent at
// all, because the server refuses it. No percent reaches the wire.
describe("program request converters", () => {
  it("submits a 10 % share as 1000 basis points and no flat fee", () => {
    const body = toProgramCreateRequest(values({ reward_amount: "10" }));
    expect(body.reward_type).toBe("revenue_share");
    expect(body.reward_share_basis_points).toBe(1000);
    expect("reward_amount_micros" in body).toBe(false);
    expect(body).not.toHaveProperty("reward_value");
  });

  it("keeps two decimal places of a share: 12.5 % is 1250 basis points", () => {
    const body = toProgramUpdateRequest(values({ reward_type: "profit_share", reward_amount: "12.5" }));
    expect(body.reward_share_basis_points).toBe(1250);
    expect("reward_amount_micros" in body).toBe(false);
    expect(body.reward_window_days).toBeNull();
    expect(body.max_reward_micros).toBeNull();
    expect(body.max_referrals_per_day).toBeNull();
  });

  it("submits a flat fee entered in currency units as micros, and no share", () => {
    const body = toProgramCreateRequest(
      values({ reward_type: "flat_fee", reward_amount: "5.5" }),
    );
    expect(body.reward_type).toBe("flat_fee");
    expect(body.reward_amount_micros).toBe(5_500_000);
    expect("reward_share_basis_points" in body).toBe(false);
  });

  it("sends the estimated cost percent as basis points, and null when cleared", () => {
    expect(
      toProgramCreateRequest(values({ estimated_cost_percent: "5" })).estimated_cost_basis_points,
    ).toBe(500);
    expect(
      toProgramUpdateRequest(values({ estimated_cost_percent: "0.25" })).estimated_cost_basis_points,
    ).toBe(25);
    expect(
      toProgramUpdateRequest(values({ estimated_cost_percent: "" })).estimated_cost_basis_points,
    ).toBeNull();
  });

  it("converts the lifetime cap to micros", () => {
    const body = toProgramCreateRequest(values({ max_reward: "500" }));
    expect(body.max_reward_micros).toBe(500_000_000);
  });

  it("round-trips a program into form values (flat fee micros → currency units)", () => {
    const form = programToFormValues({
      id: "prog-1",
      reward_type: "flat_fee",
      reward_amount_micros: 5_000_000,
      reward_share_basis_points: null,
      attribution_window_days: 30,
      reward_window_days: null,
      max_reward_micros: 250_000_000,
      estimated_cost_basis_points: null,
      max_referrals_per_day: 50,
      min_customer_age_hours: null,
      status: "active",
      created_at: "2026-03-02T09:15:00Z",
      updated_at: "2026-06-15T14:40:00Z",
    });
    expect(form.reward_amount).toBe("5");
    expect(form.max_reward).toBe("250");
    expect(form.reward_window_days).toBe("");
    expect(form.estimated_cost_percent).toBe("");
    expect(form.max_referrals_per_day).toBe("50");
  });

  it("shows a share's basis points back as a percent when editing: 1250 → 12.5", () => {
    const program = {
      id: "prog-2",
      reward_type: "revenue_share" as const,
      reward_amount_micros: null,
      reward_share_basis_points: 1250,
      attribution_window_days: 30,
      reward_window_days: 365,
      max_reward_micros: null,
      estimated_cost_basis_points: 750,
      max_referrals_per_day: null,
      min_customer_age_hours: null,
      status: "active" as const,
      created_at: "2026-03-02T09:15:00Z",
      updated_at: "2026-06-15T14:40:00Z",
    };
    const form = programToFormValues(program);
    expect(form.reward_amount).toBe("12.5");
    expect(form.estimated_cost_percent).toBe("7.5");
    // And the summary words the same figure the same way.
    expect(rewardSummary(program, "usd")).toBe("12.5% of referred revenue");
    expect(basisPointsPercentLabel(1000)).toBe("10%");
    expect(basisPointsPercentLabel(1225)).toBe("12.25%");
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
