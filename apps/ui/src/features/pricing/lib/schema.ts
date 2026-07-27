import { z } from "zod";

/** Create a rate card ("book"). */
export const bookCreateSchema = z.object({
  card_type: z.string().min(1, "Choose a card type"),
  key: z.string().min(1, "Give the card a unique key"),
  name: z.string(),
  provider_key: z.string(),
  currency: z.string(),
  is_default: z.boolean(),
});
export type BookCreateValues = z.infer<typeof bookCreateSchema>;

export const PRICING_MODELS = ["per_unit", "tiered", "fixed"] as const;

/** Add a rate. Money fields are entered in dollars and converted to micros. */
export const rateCreateSchema = z.object({
  metric_name: z.string().min(1, "Enter the metric name"),
  provider: z.string(),
  event_type: z.string(),
  pricing_model: z.string().min(1, "Choose a pricing model"),
  rate_per_unit: z
    .number({ message: "Enter a dollar amount" })
    .min(0, "Must be 0 or more"),
  unit_quantity: z
    .number({ message: "Enter a whole number of units" })
    .int("Must be a whole number")
    .min(1, "Must be at least 1"),
  fixed: z
    .number({ message: "Enter a dollar amount" })
    .min(0, "Must be 0 or more"),
  product_id: z.string(),
});
export type RateCreateValues = z.infer<typeof rateCreateSchema>;

/** A single staged change in the publish dialog. */
export const rateChangeSchema = z.object({
  metric_name: z.string().min(1, "Enter the metric name"),
  provider: z.string(),
  event_type: z.string(),
  pricing_model: z.string(),
  rate_per_unit: z
    .number({ message: "Enter a dollar amount" })
    .min(0, "Must be 0 or more"),
});
export const publishSchema = z.object({
  changes: z.array(rateChangeSchema).min(1, "Stage at least one change"),
});
export type PublishValues = z.infer<typeof publishSchema>;

/**
 * Tenant markup. `percentage` is a human percent (e.g. 2.5 → 2_500_000 micros);
 * `fixed_uplift` is dollars (→ micros).
 */
export const markupSchema = z.object({
  percentage: z
    .number({ message: "Enter a percentage" })
    .min(0, "Must be 0 or more"),
  fixed_uplift: z
    .number({ message: "Enter a dollar amount" })
    .min(0, "Must be 0 or more"),
});
export type MarkupValues = z.infer<typeof markupSchema>;
