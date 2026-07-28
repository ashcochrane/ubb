// Mock fixtures for the plans feature: "Acme AI"'s plan catalog, sized to
// demonstrate the full range of the three commercial axes — access fee,
// per-seat fee, and markup on metered compute — plus one archived plan.

import type { Plan } from "./types";

export const INITIAL_PLANS: Plan[] = [
  // Entry tier: no access fee, no seats — pure markup on metered usage.
  {
    id: "plan_starter",
    key: "starter",
    name: "Starter",
    access_fee_micros: 0,
    per_seat_micros: 0,
    markup_percentage_micros: 15_000_000, // 15%
    fixed_uplift_micros: 0,
    interval: "month",
    pricing_version: 1,
    archived_at: null,
  },
  // Mid tier: all three axes set.
  {
    id: "plan_growth",
    key: "growth",
    name: "Growth",
    access_fee_micros: 49_000_000, // $49.00/mo
    per_seat_micros: 12_000_000, // $12.00/seat/mo
    markup_percentage_micros: 20_000_000, // 20%
    fixed_uplift_micros: 0,
    interval: "month",
    pricing_version: 2,
    archived_at: null,
  },
  // Enterprise: annual billing, higher access + seat fees, lower markup.
  {
    id: "plan_enterprise",
    key: "enterprise",
    name: "Enterprise",
    access_fee_micros: 4_800_000_000, // $4,800.00/yr
    per_seat_micros: 240_000_000, // $240.00/seat/yr
    markup_percentage_micros: 10_000_000, // 10%
    fixed_uplift_micros: 0,
    interval: "year",
    pricing_version: 1,
    archived_at: null,
  },
  // Retired plan — archived, no longer offered, but still visible in history.
  {
    id: "plan_legacy_pro",
    key: "legacy-pro",
    name: "Legacy Pro",
    access_fee_micros: 99_000_000, // $99.00/mo
    per_seat_micros: 0,
    markup_percentage_micros: 25_000_000, // 25%
    fixed_uplift_micros: 0,
    interval: "month",
    pricing_version: 3,
    archived_at: "2026-05-12T00:00:00Z",
  },
];

/**
 * Plan keys with at least one customer currently assigned. Archiving one of
 * these must 409 — mirrors PlanService.archive's guard against silently
 * dropping an assigned customer's markup to the tenant default
 * (apps/platform/plans/services.py).
 */
export const ASSIGNED_PLAN_KEYS = new Set(["growth"]);
