// Zod schemas + conversion helpers for the plan forms. Money is entered in
// currency units and converted to integer micros at the submit boundary.

import { z } from "zod";

import type { PlanIn, PlanUpdateIn } from "../api/types";

/** "29.50" (currency units) → 29_500_000 integer micros. */
export function currencyToMicros(value: string): number {
  return Math.round(Number(value) * 1_000_000);
}

const MONEY_RE = /^\d+(\.\d{1,6})?$/;

/** Money input; "" is allowed and means "zero / leave unchanged" per form. */
const moneyInput = z
  .string()
  .trim()
  .refine((value) => value === "" || MONEY_RE.test(value), {
    message: "Enter a non-negative amount, like 29 or 29.50",
  });

export const INTERVAL_CHOICES = ["month", "year", "custom"] as const;
export type IntervalChoice = (typeof INTERVAL_CHOICES)[number];

export const createPlanSchema = z
  .object({
    key: z
      .string()
      .trim()
      .min(1, "A plan key is required")
      .max(64, "Plan keys are limited to 64 characters"),
    name: z
      .string()
      .trim()
      .min(1, "A plan name is required")
      .max(255, "Plan names are limited to 255 characters"),
    accessFee: moneyInput,
    perSeatFee: moneyInput,
    intervalChoice: z.enum(INTERVAL_CHOICES),
    customInterval: z.string().trim(),
  })
  .superRefine((value, ctx) => {
    if (value.intervalChoice === "custom" && value.customInterval === "") {
      ctx.addIssue({
        code: "custom",
        path: ["customInterval"],
        message: "Enter the billing interval to send",
      });
    }
  });

export type CreatePlanFormValues = z.infer<typeof createPlanSchema>;

export function toPlanIn(values: CreatePlanFormValues): PlanIn {
  return {
    key: values.key,
    name: values.name,
    access_fee_micros: values.accessFee === "" ? 0 : currencyToMicros(values.accessFee),
    per_seat_micros: values.perSeatFee === "" ? 0 : currencyToMicros(values.perSeatFee),
    interval:
      values.intervalChoice === "custom" ? values.customInterval : values.intervalChoice,
  };
}

export const editPlanSchema = z
  .object({
    key: z
      .string()
      .trim()
      .min(1, "Enter the key of the plan to edit")
      .max(64, "Plan keys are limited to 64 characters"),
    accessFee: moneyInput,
    perSeatFee: moneyInput,
    migrateExisting: z.boolean(),
  })
  .superRefine((value, ctx) => {
    if (value.accessFee === "" && value.perSeatFee === "") {
      ctx.addIssue({
        code: "custom",
        path: ["accessFee"],
        message: "Enter at least one fee to change",
      });
    }
  });

export type EditPlanFormValues = z.infer<typeof editPlanSchema>;

/** Blank fee inputs become null = "leave unchanged" on the PATCH. */
export function toPlanUpdateIn(values: EditPlanFormValues): PlanUpdateIn {
  return {
    access_fee_micros: values.accessFee === "" ? null : currencyToMicros(values.accessFee),
    per_seat_micros: values.perSeatFee === "" ? null : currencyToMicros(values.perSeatFee),
    migrate_existing: values.migrateExisting,
  };
}
