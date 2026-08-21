// Zod form schemas for the pricing dialogs. Number-bearing fields are kept as
// strings in form state (so partial input never fights the user) and
// converted to integer micros exactly once at submit time.

import { z } from "zod";

import { RATE_STRUCTURE_VALUES } from "@/lib/vocabulary";

const nonNegativeNumberString = (message: string) =>
  z
    .string()
    .trim()
    .min(1, "Required")
    .refine((value) => Number.isFinite(Number(value)) && Number(value) >= 0, {
      message,
    });

// ⚠ NO MARKUP FORM (#369). It validated a percentage beside a flat per-event
// amount, for a dialog that has not existed on this page for some time. The
// record behind it is deleted and the rung that replaced it takes ONE term —
// a margin over cost never composes with an addend — so the two-field shape
// would be wrong for the surface #372 builds as well as unused today.

// ⚠ NO `card_type` (#368). Which kind of book is being declared is which
// ROUTE the dialog calls, not a field on one body: a Pricing Book names
// neither a supplier nor a currency and a cost book names both, so one schema
// covering both would describe a shape the API does not have. The dialog holds
// the choice in its own state and hands each half the fields its own body
// takes.
export const bookFormSchema = z.object({
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
    // The registry's own set, imported rather than restated
    // (`docs/conventions/coding-standards.md` §Vocabulary: code imports a
    // registry value, it never spells the literal). A hand-typed pair here
    // would be a form that refuses a value the API accepts on the day the
    // concept moves — and this form SENDS what it validates.
    rate_structure: z.enum(RATE_STRUCTURE_VALUES),
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
