import { z } from "zod";

/** A dollar amount entered as text, converted to integer micros on submit. */
const dollarString = z
  .string()
  .refine((v) => v === "" || !Number.isNaN(Number(v)), "Enter a valid amount")
  .refine((v) => v === "" || Number(v) >= 0, "Must be zero or more");

/** Convert a dollars string to integer micros (null when blank). */
export function dollarsToMicros(value: string): number | null {
  if (value.trim() === "") return null;
  return Math.round(Number(value) * 1_000_000);
}

/** Convert integer micros back to a dollars string for form defaults. */
export function microsToDollars(micros: number | null | undefined): string {
  if (micros === null || micros === undefined) return "";
  return String(micros / 1_000_000);
}

export const generalSettingsSchema = z.object({
  billing_mode: z.enum(["meter_only", "prepaid", "postpaid"]),
  default_currency: z
    .string()
    .trim()
    .regex(/^[A-Za-z]{3}$/, "Use a 3-letter currency code, e.g. USD"),
  enforcement_mode: z.enum(["off", "monitor", "enforce"]),
  min_balance_micros: dollarString,
  soft_min_balance_micros: dollarString,
  default_task_provider_cost_limit_micros: dollarString,
  require_cost_card_coverage: z.boolean(),
  automatic_tax_enabled: z.boolean(),
  arrival_signals_enabled: z.boolean(),
});
export type GeneralSettingsValues = z.infer<typeof generalSettingsSchema>;

export const apiKeyCreateSchema = z.object({
  label: z.string().trim().max(120, "Keep the label short"),
  is_test: z.boolean(),
});
export type ApiKeyCreateValues = z.infer<typeof apiKeyCreateSchema>;

export const inviteSchema = z.object({
  email: z.string().trim().email("Enter a valid email address"),
  role: z.enum(["owner", "admin", "member"]),
});
export type InviteValues = z.infer<typeof inviteSchema>;
