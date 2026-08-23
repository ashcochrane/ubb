// Zod form schemas for the pricing dialogs. Number-bearing fields are kept as
// strings in form state (so partial input never fights the user) and
// converted to integer micros exactly once at submit time.

import { z } from "zod";

import { PRICING_METHOD_VALUES, RATE_STRUCTURE_VALUES } from "@/lib/vocabulary";

const nonNegativeNumberString = (message: string) =>
  z
    .string()
    .trim()
    .min(1, "Required")
    .refine((value) => Number.isFinite(Number(value)) && Number(value) >= 0, {
      message,
    });

// ⚠ THE KIND OF BOOK IS NOT A FIELD ON THIS BODY (#368). Which one is being
// declared is which ROUTE the dialog calls: a Pricing Book names neither a
// supplier nor a currency and a cost book names both, so one schema covering
// both would describe a shape the API does not have. The dialog holds the
// choice in its own state and hands each half the fields its own body takes.
// The discriminator that used to sit here is retired, and this commit is where
// its last console occurrence goes — so this note says what the shape IS rather
// than naming what it is not.
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

/**
 * One rule, as a tenant states it — the editor behind both the book's changes
 * and one customer's own deal.
 *
 * ⚠ **THE METHOD IS A FIELD OF THIS FORM AND NOT A DERIVED FACT**, which is
 * the console obligation spec §21 says is usually missed. An override editor
 * that took only a number would make a tenant's *"charge Acme $4 per million"*
 * silently inherit whatever method the rule it replaced used — and moving a
 * customer from a margin over cost onto a flat price is a change to the shape
 * of a negotiated deal, not a change to a number. So the method is stated, it
 * is preselected from what the customer inherits, and changing it is possible
 * and deliberate.
 *
 * ⚠ **AND IT IS A DIFFERENT FIELD FROM THE ARITHMETIC SHAPE.** `rate_structure`
 * decides which of the money terms is spent; `pricing_method` decides where the
 * number came from. The contract says a change may move either without the
 * other, so a form that fused them would be unable to express half of what the
 * API accepts.
 */
export const ruleFormSchema = z
  .object({
    measurement_key: z
      .string()
      .trim()
      .min(1, "Required")
      .max(100, "Keep the measurement key under 100 characters"),
    provider: z.string().trim().max(100, "Keep the provider under 100 characters"),
    event_type: z.string().trim().max(100, "Keep the event type under 100 characters"),
    task_type: z.string().trim().max(64, "Keep the task type under 64 characters"),
    subtask_type: z
      .string()
      .trim()
      .max(64, "Keep the subtask type under 64 characters"),
    /**
     * The tenant's own pins, keyed by the key THEY declared.
     *
     * ⚠ A RECORD AND NOT TEN NAMED FIELDS, which is ruling 15's shape rather
     * than a convenience. Ten properties here would be a second hand-written
     * list of slots to keep true, and the six-of-ten gap the slice closed was
     * exactly that list being written once and not maintained. Empty values are
     * dropped at submit, because an unpinned selector is what "" means
     * everywhere on this surface.
     */
    grouping_fields: z.record(z.string(), z.string()),
    // The registry's own sets, imported rather than restated
    // (`docs/conventions/coding-standards.md` §Vocabulary: code imports a
    // registry value, it never spells the literal). A hand-typed pair here
    // would be a form that refuses a value the API accepts on the day the
    // concept moves — and this form SENDS what it validates.
    pricing_method: z.enum(PRICING_METHOD_VALUES),
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
export type RuleFormValues = z.infer<typeof ruleFormSchema>;

/**
 * An empty rule, as both editors open on one.
 *
 * ⚠ TWELVE LINES STATED ONCE. The book's change dialog and the customer's own
 * deal both reset their form to a blank rule, and both had their own copy — so
 * a field added to the schema had to be remembered in two places, and the one
 * that was forgotten would open pre-filled with `undefined` on a form whose
 * resolver would then refuse it for a reason a tenant could not act on.
 *
 * A function rather than a constant, because form state is mutated in place:
 * a shared object would be reset INTO a form and then edited through it, and
 * the next dialog to open would inherit whatever the last one typed.
 */
export function blankRule(): RuleFormValues {
  return {
    measurement_key: "",
    provider: "",
    event_type: "",
    task_type: "",
    subtask_type: "",
    grouping_fields: {},
    pricing_method: "direct_event_price",
    rate_structure: "per_unit",
    rate: "0",
    unit_choice: "1000000",
    custom_unit: "",
    fixed: "0",
  };
}

/** Resolve the effective unit_quantity from the select + custom input pair. */
export function resolveUnitQuantity(values: {
  unit_choice: string;
  custom_unit: string;
}): number {
  if (values.unit_choice === "custom") return Number(values.custom_unit);
  return Number(values.unit_choice);
}

/** The pins a tenant actually stated — "" means unpinned, so it is dropped. */
export function statedGroupingFields(
  pins: Readonly<Record<string, string>>,
): Record<string, string> {
  return Object.fromEntries(
    Object.entries(pins)
      .map(([key, value]) => [key, value.trim()] as const)
      .filter(([, value]) => value !== ""),
  );
}

/**
 * The tenant's default markup rung — ONE term.
 *
 * ⚠ **ONE FIELD, BECAUSE A MARGIN NEVER COMPOSES** (#147 §2, #369). The form
 * this replaces validated a percentage beside a flat per-event addend, because
 * two markup records could supply one; both records are deleted and the rung
 * that remains takes a percentage and nothing else. A resolved price is
 * explicable by naming one thing, and a chain whose middle terms sit on no
 * record is what that rule exists to prevent.
 *
 * ⚠ **AND AN EMPTY STRING IS NOT ZERO.** The field is required with no default
 * for the same reason the contract makes it required: a rung of zero says
 * *charge my customer exactly what the call cost*, which is a decision, and it
 * has to be typed rather than fallen into. Withdrawing the rung is the other
 * button, not an empty box.
 */
export const markupFormSchema = z.object({
  markup_percent: nonNegativeNumberString("Enter a percentage of 0 or more"),
});
export type MarkupFormValues = z.infer<typeof markupFormSchema>;
