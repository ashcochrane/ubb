import { z } from "zod";

export const webhookCreateSchema = z.object({
  url: z.string().url("Enter a valid https URL"),
  secret: z
    .string()
    .min(16, "Use a signing secret of at least 16 characters"),
  event_types: z
    .array(z.string().min(1))
    .min(1, "Subscribe to at least one event type"),
  is_active: z.boolean(),
});
export type WebhookCreateValues = z.infer<typeof webhookCreateSchema>;

export const webhookEditSchema = z.object({
  url: z.string().url("Enter a valid https URL"),
  event_types: z.array(z.string().min(1)).min(1, "Subscribe to at least one event type"),
  is_active: z.boolean(),
});
export type WebhookEditValues = z.infer<typeof webhookEditSchema>;

export const rotateSecretSchema = z.object({
  new_secret: z.string().min(16, "Use a signing secret of at least 16 characters"),
  overlap_hours: z
    .number({ message: "Enter a number of hours" })
    .int()
    .min(0, "Must be 0 or more")
    .max(168, "Keep the overlap within a week"),
});
export type RotateSecretValues = z.infer<typeof rotateSecretSchema>;
