import { describe, expect, it } from "vitest";

import {
  billingProfileSchema,
  grantSchema,
  markupSchema,
  moneyAmount,
  percentToMicros,
} from "./schemas";

const baseGrant = {
  amount: "25",
  kind: "promo",
  expiry_mode: "none" as const,
  expires_at: "",
  expires_in_days: "",
  description: "",
};

describe("grantSchema — expiry XOR", () => {
  it("accepts a never-expiring grant", () => {
    expect(grantSchema.safeParse(baseGrant).success).toBe(true);
  });

  it("requires the date when expiring on a date", () => {
    const result = grantSchema.safeParse({ ...baseGrant, expiry_mode: "at" });
    expect(result.success).toBe(false);
    expect(
      grantSchema.safeParse({
        ...baseGrant,
        expiry_mode: "at",
        expires_at: "2026-08-15",
      }).success,
    ).toBe(true);
  });

  it("requires 1–3650 days when expiring after N days", () => {
    expect(
      grantSchema.safeParse({ ...baseGrant, expiry_mode: "days" }).success,
    ).toBe(false);
    expect(
      grantSchema.safeParse({
        ...baseGrant,
        expiry_mode: "days",
        expires_in_days: "4000",
      }).success,
    ).toBe(false);
    expect(
      grantSchema.safeParse({
        ...baseGrant,
        expiry_mode: "days",
        expires_in_days: "90",
      }).success,
    ).toBe(true);
  });
});

describe("moneyAmount", () => {
  it("rejects blanks, non-numbers, and non-positive amounts", () => {
    expect(moneyAmount.safeParse("").success).toBe(false);
    expect(moneyAmount.safeParse("abc").success).toBe(false);
    expect(moneyAmount.safeParse("0").success).toBe(false);
    expect(moneyAmount.safeParse("-5").success).toBe(false);
    expect(moneyAmount.safeParse("12.34").success).toBe(true);
  });
});

describe("billingProfileSchema — floor wire semantics", () => {
  const base = { min_balance: "", soft_min_balance: "", topup_grant_expiry_days: "" };

  it("accepts all-blank (inherit everything)", () => {
    expect(billingProfileSchema.safeParse(base).success).toBe(true);
  });

  it("rejects a negative allowed overdraft (the wire field is a magnitude ≥ 0)", () => {
    const result = billingProfileSchema.safeParse({ ...base, min_balance: "-50" });
    expect(result.success).toBe(false);
    expect(
      billingProfileSchema.safeParse({ ...base, min_balance: "0" }).success,
    ).toBe(true);
    expect(
      billingProfileSchema.safeParse({ ...base, min_balance: "25" }).success,
    ).toBe(true);
  });

  it("rejects a wind-down value deeper than the allowed overdraft (soft ≤ hard)", () => {
    expect(
      billingProfileSchema.safeParse({
        ...base,
        min_balance: "25",
        soft_min_balance: "30",
      }).success,
    ).toBe(false);
    expect(
      billingProfileSchema.safeParse({
        ...base,
        min_balance: "25",
        soft_min_balance: "20",
      }).success,
    ).toBe(true);
  });

  it("accepts a NEGATIVE wind-down wire value (line above zero)", () => {
    expect(
      billingProfileSchema.safeParse({
        ...base,
        min_balance: "25",
        soft_min_balance: "-50",
      }).success,
    ).toBe(true);
  });
});

describe("markup", () => {
  it("converts a human percentage to percentage-micros (1e6 = 1%)", () => {
    expect(percentToMicros("25")).toBe(25_000_000);
    expect(percentToMicros("2.5")).toBe(2_500_000);
    expect(percentToMicros("0")).toBe(0);
  });

  it("allows a 0/0 override (which pins the customer at cost)", () => {
    expect(markupSchema.safeParse({ percent: "0", uplift: "0" }).success).toBe(true);
    expect(markupSchema.safeParse({ percent: "-1", uplift: "0" }).success).toBe(false);
  });
});
