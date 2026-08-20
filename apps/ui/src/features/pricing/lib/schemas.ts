// Zod form schemas for the pricing dialogs. Number-bearing fields are kept as
// strings in form state (so partial input never fights the user) and
// converted to integer micros exactly once at submit time.

import { z } from "zod";

const nonNegativeNumberString = (message: string) =>
  z
    .string()
    .trim()
    .min(1, "Required")
    .refine((value) => Number.isFinite(Number(value)) && Number(value) >= 0, {
      message,
    });

export const markupFormSchema = z.object({
  percent: nonNegativeNumberString("Enter a percentage of 0 or more"),
  fixed: nonNegativeNumberString("Enter an amount of 0 or more"),
});
export type MarkupFormValues = z.infer<typeof markupFormSchema>;

export const bookFormSchema = z.object({
  card_type: z.enum(["cost", "price"]),
  key: z
    .string()
    .trim()
    .min(1, "Required")
    .max(64, "Keep the key under 64 characters"),
  name: z.string().trim().max(255, "Keep the name under 255 characters"),
  provider_key: z.string().trim().max(100, "Keep the provider under 100 characters"),
  is_default: z.boolean(),
});
export type BookFormValues = z.infer<typeof bookFormSchema>;

export const rateFormSchema = z
  .object({
    measurement_key: z
      .string()
      .trim()
      .min(1, "Required")
      .max(100, "Keep the measurement key under 100 characters"),
    provider: z.string().trim().max(100, "Keep the provider under 100 characters"),
    event_type: z.string().trim().max(100, "Keep the event type under 100 characters"),
    task_type: z.string().trim().max(64, "Keep the task type under 64 characters"),
    rate_structure: z.enum(["per_unit", "fixed_component"]),
    rate: nonNegativeNumberString("Enter an amount of 0 or more"),
    unit_choice: z.enum(["1", "1000", "1000000", "custom"]),
    custom_unit: z.string().trim(),
    fixed: nonNegativeNumberString("Enter an amount of 0 or more"),
  })
  .superRefine((values, ctx) => {
    if (values.unit_choice === "custom") {
      const quantity = Number(values.custom_unit);
      if (!Number.isInteger(quantity) || quantity <= 0) {
        ctx.addIssue({
          code: "custom",
          path: ["custom_unit"],
          message: "Enter a whole number of units greater than 0",
        });
      }
    }
  });
export type RateFormValues = z.infer<typeof rateFormSchema>;

/** Resolve the effective unit_quantity from the select + custom input pair. */
export function resolveUnitQuantity(values: {
  unit_choice: string;
  custom_unit: string;
}): number {
  if (values.unit_choice === "custom") return Number(values.custom_unit);
  return Number(values.unit_choice);
}
