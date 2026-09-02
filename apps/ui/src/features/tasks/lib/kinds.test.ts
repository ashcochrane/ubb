import { describe, expect, it } from "vitest";

import type { TenantConfig } from "@/hooks/use-tenant-config";
import { PRICING_MODE_VALUES } from "@/lib/vocabulary";

import type { KindOfWork } from "../api/types";
import {
  alreadyDeclared,
  altitudeLabel,
  ceilingShare,
  declarationBody,
  declarationNotes,
  declarationsUnderKey,
  describeCeiling,
  describeDuration,
  describeShare,
  effectiveCeiling,
  pricedRuns,
  PRICING_MODE_EXPLANATIONS,
  pricingModeLabel,
  REGIME_CANNOT_CHANGE,
  REGIME_IS_INERT_UNTIL_BILLING,
  sortedKinds,
} from "./kinds";

function kind(overrides: Partial<KindOfWork> & Pick<KindOfWork, "key">): KindOfWork {
  return {
    kind: "task",
    pricing_mode: "event_priced",
    default_provider_cost_limit_micros: null,
    silence_window_seconds: null,
    absolute_deadline_seconds: null,
    required_dimensions: [],
    retired: false,
    retired_at: null,
    ...overrides,
  };
}

function config(defaultCeiling: number | null): TenantConfig {
  return {
    name: "Acme AI",
    billing_mode: "prepaid",
    products: ["metering", "billing"],
    default_currency: "usd",
    stripe_connected_account_id: "acct_test",
    is_active: true,
    automatic_tax_enabled: false,
    enforcement_mode: "enforcing",
    live_counter_maintenance_enabled: true,
    min_balance_micros: 0,
    soft_min_balance_micros: null,
    default_task_provider_cost_limit_micros: defaultCeiling,
  };
}

describe("the words for how a kind of work is sold", () => {
  it("are the catalogue's, bound at this surface", () => {
    expect(pricingModeLabel("event_priced")).toBe("Event priced");
    expect(pricingModeLabel("fixed")).toBe("Fixed price");
    expect(altitudeLabel("task")).toBe("Task");
    expect(altitudeLabel("subtask")).toBe("Subtask");
  });

  it("render a value the registry has never seen as itself, never humanised", () => {
    expect(pricingModeLabel("some_future_regime")).toBe("some_future_regime");
  });

  it("explain every regime the registry declares", () => {
    expect(Object.keys(PRICING_MODE_EXPLANATIONS).sort()).toEqual(
      [...PRICING_MODE_VALUES].sort(),
    );
  });
});

describe("what a tenant is told at declaration time", () => {
  it("tells a metering-only workspace both things, the refusal first", () => {
    expect(declarationNotes({ meteringOnly: true })).toEqual([
      REGIME_IS_INERT_UNTIL_BILLING,
      REGIME_CANNOT_CHANGE,
    ]);
  });

  it("tells a billing workspace only that the regime is frozen", () => {
    expect(declarationNotes({ meteringOnly: false })).toEqual([REGIME_CANNOT_CHANGE]);
  });

  it("names the start-gate refusal and the retire-and-redeclare path in so many words", () => {
    expect(REGIME_IS_INERT_UNTIL_BILLING).toMatch(/refuses to start/);
    expect(REGIME_IS_INERT_UNTIL_BILLING).toMatch(/billing is enabled/);
    expect(REGIME_CANNOT_CHANGE).toMatch(/cannot be changed/);
    expect(REGIME_CANNOT_CHANGE).toMatch(/retire/);
    expect(REGIME_CANNOT_CHANGE).toMatch(/new key/);
  });
});

describe("the ceiling a kind of work actually runs under", () => {
  it("is the declaration's own when it names one", () => {
    expect(
      effectiveCeiling(kind({ key: "k", default_provider_cost_limit_micros: 3_000_000 }), config(9_000_000)),
    ).toEqual({ source: "declaration", micros: 3_000_000 });
  });

  it("falls back to the workspace default, then to uncapped — never silently", () => {
    expect(effectiveCeiling(kind({ key: "k" }), config(9_000_000))).toEqual({
      source: "workspace",
      micros: 9_000_000,
    });
    expect(effectiveCeiling(kind({ key: "k" }), config(null))).toEqual({ source: "uncapped" });
  });

  it("is unknown while the workspace config has not arrived, rather than uncapped", () => {
    expect(effectiveCeiling(kind({ key: "k" }), undefined)).toBeNull();
  });

  it("is described so that none, not-yet-known and a number read differently", () => {
    expect(describeCeiling({ source: "declaration", micros: 3_000_000 }, "usd")).toBe("$3.00");
    expect(describeCeiling({ source: "workspace", micros: 9_000_000 }, "usd")).toBe(
      "$9.00 (workspace default)",
    );
    expect(describeCeiling({ source: "uncapped" }, "usd")).toBe("Uncapped");
    expect(describeCeiling(null, "usd")).toBe("—");
  });
});

describe("a duration", () => {
  it("reads as a person would say it, and an absent one is left for the caller to name", () => {
    expect(describeDuration(600)).toBe("10 min");
    expect(describeDuration(7_200)).toBe("2 h");
    expect(describeDuration(90)).toBe("90 s");
    expect(describeDuration(null)).toBeNull();
    expect(describeDuration(undefined)).toBeNull();
  });
});

describe("the order kinds of work are listed in", () => {
  it("puts live ones before retired ones, and each half by key", () => {
    const listed = sortedKinds([
      kind({ key: "zeta", retired: true }),
      kind({ key: "beta" }),
      kind({ key: "alpha", retired: true }),
      kind({ key: "gamma" }),
    ]).map((k) => k.key);
    expect(listed).toEqual(["beta", "gamma", "alpha", "zeta"]);
  });
});

describe("the price a kind of work sold for, read off its runs", () => {
  it("is absent when no run has pinned a price", () => {
    expect(pricedRuns([])).toBeNull();
    expect(pricedRuns([{ agreed_price_micros: null }, {}])).toBeNull();
  });

  it("is one figure when every run was quoted the same", () => {
    expect(
      pricedRuns([
        { agreed_price_micros: 5_000_000 },
        { agreed_price_micros: 5_000_000 },
        { agreed_price_micros: null },
      ]),
    ).toEqual({ lowMicros: 5_000_000, highMicros: 5_000_000, runCount: 2 });
  });

  it("is a range when different customers' books priced it differently", () => {
    expect(
      pricedRuns([{ agreed_price_micros: 8_000_000 }, { agreed_price_micros: 4_000_000 }]),
    ).toEqual({ lowMicros: 4_000_000, highMicros: 8_000_000, runCount: 2 });
  });

  it("states the ceiling as a share of the price — #150 §5.4's own arithmetic", () => {
    expect(ceilingShare(3_000_000, 5_000_000)).toBeCloseTo(0.6);
    expect(ceilingShare(3_000_000, 8_000_000)).toBeCloseTo(0.375);
  });

  it("says the share as a whole percentage, floored — never overstating the headroom", () => {
    expect(describeShare(3_000_000, 5_000_000)).toBe("60%");
    expect(describeShare(3_000_000, 8_000_000)).toBe("37%");
  });

  it("has no share to say against a run quoted at no charge", () => {
    expect(describeShare(3_000_000, 0)).toBeNull();
  });
});

describe("whether a declaration already stands", () => {
  it("is decided by the word and the altitude together", () => {
    const standing = [kind({ key: "translate" }), kind({ key: "render-frame", kind: "subtask" })];
    expect(alreadyDeclared(standing, { kind: "task", key: "translate" })).toBe(true);
    expect(alreadyDeclared(standing, { kind: "subtask", key: "translate" })).toBe(false);
    expect(alreadyDeclared(standing, { kind: "task", key: "render-frame" })).toBe(false);
  });
});

describe("a declaration body", () => {
  const standingA = kind({
    key: "document-summary",
    default_provider_cost_limit_micros: 2_000_000,
    silence_window_seconds: 600,
    required_dimensions: ["model"],
  });
  const standingB = kind({
    key: "legacy-ocr",
    pricing_mode: "fixed",
    retired: true,
    retired_at: "2026-06-30T09:00:00Z",
  });

  it("re-declares every standing kind verbatim beside the new one", () => {
    const body = declarationBody(
      [standingA, standingB],
      { key: "video-render", kind: "task", pricing_mode: "fixed", required_dimensions: [] },
    );
    expect(body.task_types).toHaveLength(3);
    expect(body.task_types[0]).toEqual({
      key: "document-summary",
      kind: "task",
      pricing_mode: "event_priced",
      default_provider_cost_limit_micros: 2_000_000,
      silence_window_seconds: 600,
      absolute_deadline_seconds: null,
      required_dimensions: ["model"],
      retired: false,
    });
    expect(body.task_types[1]).toMatchObject({ key: "legacy-ocr", retired: true });
    expect(body.task_types[1]).not.toHaveProperty("retired_at");
    expect(body.task_types[2]).toMatchObject({ key: "video-render", pricing_mode: "fixed" });
  });

  it("replaces a standing declaration in place, keeping the regime it already holds", () => {
    const body = declarationBody([standingA, standingB], {
      key: "document-summary",
      kind: "task",
      default_provider_cost_limit_micros: 4_000_000,
      required_dimensions: ["model"],
    });
    expect(body.task_types).toHaveLength(2);
    expect(body.task_types[0]).toMatchObject({
      key: "document-summary",
      pricing_mode: "event_priced",
      default_provider_cost_limit_micros: 4_000_000,
      silence_window_seconds: null,
    });
  });

  it("treats the same word at two altitudes as two declarations", () => {
    const contained = kind({ key: "document-summary", kind: "subtask" });
    const body = declarationBody([standingA, contained], {
      key: "document-summary",
      kind: "subtask",
      default_provider_cost_limit_micros: 250_000,
      required_dimensions: [],
    });
    expect(body.task_types).toHaveLength(2);
    expect(body.task_types[0]).toMatchObject({ kind: "task", default_provider_cost_limit_micros: 2_000_000 });
    expect(body.task_types[1]).toMatchObject({ kind: "subtask", default_provider_cost_limit_micros: 250_000 });
  });
});

describe("the declarations a routed key names", () => {
  it("lists the whole-work altitude first and nothing under another key", () => {
    const contained = kind({ key: "translate", kind: "subtask" });
    const whole = kind({ key: "translate" });
    const other = kind({ key: "video-render" });
    expect(declarationsUnderKey([contained, other, whole], "translate")).toEqual([whole, contained]);
    expect(declarationsUnderKey([contained, other, whole], "nothing-here")).toEqual([]);
  });
});
