import { describe, expect, it } from "vitest";

import type { MarginThreshold, TenantConfig } from "../api/types";
import {
  auditActionLabel,
  buildSpendPatch,
  inputToMicros,
  marginAlertSchema,
  spendControlSchema,
  thresholdToValues,
  truncateId,
  valuesToThreshold,
} from "./settings";

const baseConfig: TenantConfig = {
  name: "Acme AI",
  billing_mode: "prepaid",
  products: ["metering", "billing"],
  require_cost_card_coverage: false,
  default_currency: "usd",
  stripe_connected_account_id: "acct_1",
  is_active: true,
  automatic_tax_enabled: false,
  enforcement_mode: "enforcing",
  live_counter_maintenance_enabled: true,
  min_balance_micros: 25_000_000,
  soft_min_balance_micros: -10_000_000,
  default_task_provider_cost_limit_micros: 5_000_000,
};

describe("inputToMicros", () => {
  it("converts currency units to integer micros", () => {
    expect(inputToMicros("25")).toBe(25_000_000);
    expect(inputToMicros("0.01")).toBe(10_000);
    expect(inputToMicros("-10.5")).toBe(-10_500_000);
  });
});

describe("buildSpendPatch — PATCH partial semantics", () => {
  it("returns an empty patch when nothing changed", () => {
    expect(
      buildSpendPatch(baseConfig, {
        allowedOverdraft: "25",
        softFloor: "-10",
        taskLimit: "5",
      }),
    ).toEqual({});
  });

  it("sends only the changed field", () => {
    const patch = buildSpendPatch(baseConfig, {
      allowedOverdraft: "50",
      softFloor: "-10",
      taskLimit: "5",
    });
    expect(patch).toEqual({ min_balance_micros: 50_000_000 });
  });

  it("clearing a clearable field sends an EXPLICIT null", () => {
    const patch = buildSpendPatch(baseConfig, {
      allowedOverdraft: "25",
      softFloor: "",
      taskLimit: "",
    });
    expect(patch).toEqual({
      soft_min_balance_micros: null,
      default_task_provider_cost_limit_micros: null,
    });
    // Explicit nulls, not absent keys — the server treats them differently.
    expect("soft_min_balance_micros" in patch).toBe(true);
  });
});

describe("spendControlSchema — wire sign convention (soft value ≤ hard value)", () => {
  it("accepts a negative wind-down value (line above zero — early wind-down)", () => {
    // Wire value −30 places the wind-down line at +30, validly above the
    // −25 hard stop line. The old client wrongly blocked this.
    const result = spendControlSchema.safeParse({
      allowedOverdraft: "25",
      softFloor: "-30",
      taskLimit: "",
    });
    expect(result.success).toBe(true);
  });

  it("accepts a wind-down value equal to the allowed overdraft (both lines coincide)", () => {
    const result = spendControlSchema.safeParse({
      allowedOverdraft: "25",
      softFloor: "25",
      taskLimit: "",
    });
    expect(result.success).toBe(true);
  });

  it("rejects a wind-down value above the allowed overdraft (line below the hard stop)", () => {
    // Wire value 30 would place the wind-down line at −30, below the −25
    // hard stop line — the server 422s this; the old client wrongly allowed it.
    const result = spendControlSchema.safeParse({
      allowedOverdraft: "25",
      softFloor: "30",
      taskLimit: "",
    });
    expect(result.success).toBe(false);
  });

  it("rejects a zero task limit but allows empty (no limit)", () => {
    expect(
      spendControlSchema.safeParse({
        allowedOverdraft: "0",
        softFloor: "",
        taskLimit: "0",
      }).success,
    ).toBe(false);
    expect(
      spendControlSchema.safeParse({
        allowedOverdraft: "0",
        softFloor: "",
        taskLimit: "",
      }).success,
    ).toBe(true);
  });
});

describe("margin-alert form helpers", () => {
  const threshold: MarginThreshold = {
    min_margin_pct: 12.5,
    consecutive_periods: 2,
    provider_cost_spike_pct: 25,
  };

  it("round-trips an untouched prefill byte-identically (full precision, no toFixed)", () => {
    const values = thresholdToValues(threshold);
    expect(values).toEqual({
      minMarginPct: "12.5",
      consecutivePeriods: "2",
      providerCostSpikePct: "25",
    });
    expect(valuesToThreshold(values)).toEqual({
      min_margin_pct: 12.5,
      consecutive_periods: 2,
      provider_cost_spike_pct: 25,
    });
  });

  it("mirrors only the server's constraints: periods must be a whole number ≥ 1", () => {
    const base = {
      minMarginPct: "0",
      providerCostSpikePct: "25",
    };
    expect(
      marginAlertSchema.safeParse({ ...base, consecutivePeriods: "1" }).success,
    ).toBe(true);
    expect(
      marginAlertSchema.safeParse({ ...base, consecutivePeriods: "0" }).success,
    ).toBe(false);
    expect(
      marginAlertSchema.safeParse({ ...base, consecutivePeriods: "1.5" }).success,
    ).toBe(false);
    // Percent fields carry no server constraint beyond being numbers.
    expect(
      marginAlertSchema.safeParse({
        minMarginPct: "-10",
        consecutivePeriods: "3",
        providerCostSpikePct: "40",
      }).success,
    ).toBe(true);
  });
});

describe("auditActionLabel", () => {
  it("humanizes noun.verb actions", () => {
    expect(auditActionLabel("config.updated")).toBe("Config updated");
    expect(auditActionLabel("member.role_updated")).toBe("Member role updated");
  });

  it("special-cases API key and tolerates undotted actions", () => {
    expect(auditActionLabel("api_key.rotated")).toBe("API key rotated");
    expect(auditActionLabel("login")).toBe("Login");
  });
});

describe("truncateId", () => {
  it("truncates long ids and leaves short ones alone", () => {
    expect(truncateId("rc-openai-price-v4", 8)).toBe("rc-opena…");
    expect(truncateId("short", 8)).toBe("short");
  });
});
