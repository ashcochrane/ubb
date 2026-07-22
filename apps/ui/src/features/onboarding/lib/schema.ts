import { z } from "zod";

export const onboardingSchema = z.object({
  tenantName: z
    .string()
    .trim()
    .min(1, "Workspace name is required")
    .max(255, "Workspace name must be 255 characters or less"),
});

export type OnboardingFormValues = z.infer<typeof onboardingSchema>;
