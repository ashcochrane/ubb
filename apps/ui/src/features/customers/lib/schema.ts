import { z } from "zod";

export const customerCreateSchema = z.object({
  external_id: z.string().min(1, "External ID is required"),
  stripe_customer_id: z.string().optional(),
  account_type: z.enum(["individual", "business"]),
  parent_external_id: z.string().optional(),
  billing_topology: z.string().optional(),
});
export type CustomerCreateValues = z.infer<typeof customerCreateSchema>;

export const grantSchema = z.object({
  kind: z.string().min(1, "Kind is required"),
  amount: z.number().positive("Amount must be greater than 0"),
  expires_in_days: z.number().int().positive().optional(),
  description: z.string().optional(),
});
export type GrantValues = z.infer<typeof grantSchema>;

export const budgetSchema = z.object({
  cap: z.number().nonnegative("Cap must be 0 or more"),
  enforce_mode: z.enum(["advisory", "monitor", "enforce"]),
  hard_stop_pct: z.number().int().min(0).max(1000),
  fail_closed: z.boolean(),
});
export type BudgetValues = z.infer<typeof budgetSchema>;

export const billingProfileSchema = z.object({
  min_balance: z.number().optional(),
  soft_min_balance: z.number().optional(),
  topup_grant_expiry_days: z.number().int().positive().optional(),
});
export type BillingProfileValues = z.infer<typeof billingProfileSchema>;

export const markupSchema = z.object({
  markup_percentage: z.number().min(0, "Must be 0 or more"),
  fixed_uplift: z.number().min(0, "Must be 0 or more"),
});
export type MarkupValues = z.infer<typeof markupSchema>;

export const revenueProfileSchema = z.object({
  recurring_amount: z.number().nonnegative("Must be 0 or more"),
  interval: z.enum(["month", "year"]),
  currency: z.string().optional(),
});
export type RevenueProfileValues = z.infer<typeof revenueProfileSchema>;

export const subscribeSchema = z.object({
  plan_key: z.string().min(1, "Plan key is required"),
  seats: z.number().int().min(0),
});
export type SubscribeValues = z.infer<typeof subscribeSchema>;

export const seatsSchema = z.object({
  seats: z.number().int().min(0, "Seats must be 0 or more"),
});
export type SeatsValues = z.infer<typeof seatsSchema>;
