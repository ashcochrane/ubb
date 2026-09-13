// The seat-default pool's declaration form — the workspace's Customer Spend
// Pool for every seat that declares none of its own (#468; slice 6 §4, §18).
//
// SPLIT OUT OF `./billing-forms` BEFORE THAT FILE WAS TOUCHED (spec §20): the
// forms module carries words a later slice retires, which this slice may
// reduce and may not raise, so the pool's form left it whole and took the
// family's name here. The currency helpers stay there and are shared.
//
// The PUT is a FULL upsert with schema defaults, so every field is always
// sent. The mode is the registry's CLOSED pair held by reference from the
// generated vocabulary — there is no unknown value to narrow, and the
// generated read type already says so.

import { z } from "zod";

import { SPEND_POOL_ENFORCE_MODE_VALUES } from "@/lib/vocabulary";

import type { CustomerSpendPool, CustomerSpendPoolIn } from "../api/types";
import { currencyAmountField, currencyToMicros, microsToCurrencyInput } from "./billing-forms";

export const customerSpendPoolFormSchema = z.object({
  cap: currencyAmountField({ min: 0 }),
  enforce_mode: z.enum(SPEND_POOL_ENFORCE_MODE_VALUES),
  hard_stop_pct: z
    .string()
    .min(1, "Required")
    .refine((v) => /^\d+$/.test(v), "Whole number")
    .refine((v) => Number(v) >= 1 && Number(v) <= 1000, "Between 1 and 1000"),
  alert_levels: z.array(z.number().int().min(1).max(1000)),
  fail_closed: z.boolean(),
});

export type CustomerSpendPoolFormValues = z.infer<typeof customerSpendPoolFormSchema>;

export function customerSpendPoolToFormValues(pool: CustomerSpendPool): CustomerSpendPoolFormValues {
  return {
    cap: microsToCurrencyInput(pool.cap_micros),
    enforce_mode: pool.enforce_mode,
    hard_stop_pct: String(pool.hard_stop_pct),
    alert_levels: [...pool.alert_levels].sort((a, b) => a - b),
    fail_closed: pool.fail_closed,
  };
}

/** Full-upsert body: every field is always present. */
export function customerSpendPoolFormToPayload(
  values: CustomerSpendPoolFormValues,
): CustomerSpendPoolIn {
  return {
    cap_micros: currencyToMicros(values.cap),
    enforce_mode: values.enforce_mode,
    hard_stop_pct: Number(values.hard_stop_pct),
    alert_levels: values.alert_levels,
    fail_closed: values.fail_closed,
  };
}
