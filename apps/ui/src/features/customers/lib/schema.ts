import { z } from "zod";

export const customerCreateSchema = z.object({
  externalId: z.string().trim().min(1, "External ID is required"),
  stripeCustomerId: z.string().trim(),
});

export type CustomerCreateFormValues = z.infer<typeof customerCreateSchema>;

export const customerEditSchema = z.object({
  stripeCustomerId: z.string().trim(),
  status: z.enum(["active", "suspended", "archived"]),
});

export type CustomerEditFormValues = z.infer<typeof customerEditSchema>;
