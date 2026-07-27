import { z } from "zod";

/**
 * Margin threshold form. All three fields drive the unprofitability alerting
 * pipeline (min_margin_pct is a plain percentage number, not micros).
 */
export const thresholdSchema = z.object({
  min_margin_pct: z
    .number({ message: "Enter a percentage" })
    .min(-100, "Can't be below -100%")
    .max(100, "Can't exceed 100%"),
  consecutive_periods: z
    .number({ message: "Enter a whole number" })
    .int("Whole periods only")
    .min(1, "At least one period"),
  provider_cost_spike_pct: z
    .number({ message: "Enter a percentage" })
    .min(0, "Can't be negative"),
});
export type ThresholdValues = z.infer<typeof thresholdSchema>;
