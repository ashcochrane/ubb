import { z } from "zod";

export const dimensionSchema = z.object({
  key: z.string().min(1, "Required").max(60),
  type: z.enum(["per_unit", "flat"]),
  price: z.number().min(0, "Must be non-negative"),
  label: z.string().min(1, "Required").max(100),
  unit: z.string().max(50),
  displayPrice: z.string().optional(),
});

export const wizardSchema = z.object({
  sourceType: z.enum(["template", "custom"]),
  templateId: z.string().optional(),
  name: z.string().min(1, "Card name is required").max(250),
  provider: z.string().min(1, "Provider is required"),
  providerCustom: z.string().optional(),
  cardId: z.string().min(1, "Card ID is required").max(40),
  pricingPattern: z.enum(["token", "request", "mixed"]),
  description: z.string().max(250).optional(),
  pricingSourceUrl: z.string().url().optional().or(z.literal("")),
  dimensions: z.array(dimensionSchema).min(1, "At least one dimension required"),
  product: z.string().optional(),
});

export type WizardFormValues = z.infer<typeof wizardSchema>;
