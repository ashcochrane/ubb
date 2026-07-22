import { z } from "zod";

export const dimensionInputSchema = z.object({
  metricName: z.string().min(1, "Required").regex(/^[a-z][a-z0-9_]*$/, "Must be snake_case"),
  pricingType: z.enum(["per_unit", "flat"]),
  costPerUnitMicros: z.number().int().min(0),
  providerCostPerUnitMicros: z.number().int().min(0).nullable(),
  unitQuantity: z.number().int().min(1),
  currency: z.string().min(1).max(3),
  label: z.string(),
  unit: z.string(),
});

export const cardFormSchema = z.object({
  name: z.string().min(1, "Required").max(255),
  slug: z.string().min(2).max(255).regex(/^[a-z][a-z0-9_]*$/, "Must be snake_case"),
  provider: z.string().min(1).max(100),
  description: z.string(),
  pricingSourceUrl: z.string(),
  groupId: z.string().nullable(),
  status: z.enum(["draft", "active", "archived"]),
  dimensions: z.array(dimensionInputSchema),
});

export type CardFormValues = z.infer<typeof cardFormSchema>;

// Wizard wraps the card form with extra UI-only fields
export const wizardSchema = cardFormSchema.extend({
  sourceType: z.enum(["template", "custom"]),
  templateId: z.string().optional(),
});

export type WizardFormValues = z.infer<typeof wizardSchema>;

// ── Rate add/edit dialog ──────────────────────────────────────────────────────

export const rateSchema = z.object({
  metricName: z.string().trim().min(1, "Metric name is required"),
  label: z.string(),
  unit: z.string(),
  unitQuantity: z.number().int().min(1),
  pricingType: z.enum(["per_unit", "flat"]),
  costPerUnitMicros: z.number().int().min(0),
  providerCostPerUnitMicros: z.number().int().min(0).nullable(),
});

export type RateFormValues = z.infer<typeof rateSchema>;

// ── Card edit form ────────────────────────────────────────────────────────────

export const cardEditSchema = z.object({
  name: z.string().trim().min(1, "Name is required"),
  description: z.string(),
  pricingSourceUrl: z.string(),
  groupId: z.string().nullable(),
});

export type CardEditFormValues = z.infer<typeof cardEditSchema>;
