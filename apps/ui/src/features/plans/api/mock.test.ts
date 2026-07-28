import { beforeEach, describe, expect, it, vi } from "vitest";

import type * as PlansMock from "./mock";

// The mock keeps its plan list as module-level state so mutations persist
// within a session (create -> list shows it). Reset modules and re-import
// before each test so tests don't leak state into each other.
let mock: typeof PlansMock;

beforeEach(async () => {
  vi.resetModules();
  mock = await import("./mock");
});

describe("plans mock provider", () => {
  it("lists the seeded plans, demonstrating the full fee range", async () => {
    const { plans } = await mock.listPlans();
    expect(plans.map((plan) => plan.key)).toEqual([
      "starter",
      "growth",
      "enterprise",
      "legacy-pro",
    ]);
    // Entry tier: markup-only, no access or seat fee.
    expect(plans[0]).toMatchObject({ access_fee_micros: 0, per_seat_micros: 0 });
    // Mid tier: all three axes set.
    expect(plans[1]).toMatchObject({
      access_fee_micros: 49_000_000,
      per_seat_micros: 12_000_000,
      markup_percentage_micros: 20_000_000,
    });
    // One archived plan is visible in the catalog.
    expect(plans.find((plan) => plan.archived_at !== null)?.key).toBe("legacy-pro");
  });

  it("creates a plan that then appears in the list", async () => {
    const created = await mock.createPlan({
      key: "solo",
      name: "Solo",
      access_fee_micros: 0,
      per_seat_micros: 0,
      markup_percentage_micros: 18_000_000,
      fixed_uplift_micros: 0,
      interval: "month",
    });
    expect(created.key).toBe("solo");
    expect(created.pricing_version).toBe(1);
    expect(created.archived_at).toBeNull();

    const { plans } = await mock.listPlans();
    expect(plans.some((plan) => plan.key === "solo")).toBe(true);
  });

  it("409s creating a plan with a duplicate key", async () => {
    await expect(
      mock.createPlan({
        key: "growth",
        name: "Growth Clone",
        access_fee_micros: 0,
        per_seat_micros: 0,
        markup_percentage_micros: 0,
        fixed_uplift_micros: 0,
        interval: "month",
      }),
    ).rejects.toMatchObject({ status: 409 });
  });

  it("bumps pricing_version on a fee change but not on a markup-only change", async () => {
    const feeChange = await mock.updatePlan("enterprise", {
      access_fee_micros: 5_000_000_000,
      migrate_existing: false,
    });
    expect(feeChange.pricing_version).toBe(2);

    const markupOnly = await mock.updatePlan("enterprise", {
      markup_percentage_micros: 11_000_000,
      migrate_existing: false,
    });
    expect(markupOnly.pricing_version).toBe(2);
    expect(markupOnly.markup_percentage_micros).toBe(11_000_000);
  });

  it("archives a plan with no assigned customers", async () => {
    await mock.archivePlan("enterprise");
    const { plans } = await mock.listPlans();
    const plan = plans.find((candidate) => candidate.key === "enterprise");
    expect(plan?.archived_at).not.toBeNull();
  });

  it("409s archiving a plan that still has customers assigned", async () => {
    await expect(mock.archivePlan("growth")).rejects.toMatchObject({ status: 409 });
  });
});
