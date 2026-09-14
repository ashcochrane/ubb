import { describe, expect, it } from "vitest";

import { SPEND_POOL_ENFORCE_MODE_VALUES } from "@/lib/vocabulary";

import {
  customerSpendPoolFormSchema,
  customerSpendPoolFormToPayload,
  customerSpendPoolToFormValues,
} from "./customer-spend-pool-form";

describe("the seat-default pool's form (full upsert)", () => {
  it("round-trips the GET payload and always submits every field", () => {
    const values = customerSpendPoolToFormValues({
      cap_micros: 2_500_000_000,
      enforce_mode: "alert_only",
      hard_stop_pct: 120,
      alert_levels: [80, 50, 100],
      fail_closed: false,
    });
    expect(values.cap).toBe("2500");
    expect(values.alert_levels).toEqual([50, 80, 100]); // sorted for display

    const payload = customerSpendPoolFormToPayload(values);
    // A full upsert: every field present, even ones the user never touched.
    expect(payload).toEqual({
      cap_micros: 2_500_000_000,
      enforce_mode: "alert_only",
      hard_stop_pct: 120,
      alert_levels: [50, 80, 100],
      fail_closed: false,
    });
  });

  it("admits exactly the registry's two modes, by reference", () => {
    for (const mode of SPEND_POOL_ENFORCE_MODE_VALUES) {
      expect(
        customerSpendPoolFormSchema.safeParse({
          cap: "10",
          enforce_mode: mode,
          hard_stop_pct: "100",
          alert_levels: [],
          fail_closed: false,
        }).success,
      ).toBe(true);
    }
    expect(
      customerSpendPoolFormSchema.safeParse({
        cap: "10",
        enforce_mode: "advisory",
        hard_stop_pct: "100",
        alert_levels: [],
        fail_closed: false,
      }).success,
    ).toBe(false);
  });
});
