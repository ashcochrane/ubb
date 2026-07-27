import { z } from "zod";

/** Optional numeric text field — blank is allowed, non-numeric is rejected. */
const numericText = z
  .string()
  .refine((v) => v.trim() === "" || !Number.isNaN(Number(v)), "Must be a number");

/**
 * Record-usage advanced form. Numeric fields are kept as text so blank inputs
 * stay blank (rather than coercing to NaN); they are parsed on submit. Dollar
 * amounts are converted to `*_micros` integers via Math.round($ * 1e6).
 * `request_id` / `idempotency_key` are generated at submit with crypto.randomUUID().
 */
export const recordUsageSchema = z.object({
  customer_id: z.string().min(1, "Customer ID is required"),
  event_type: z.string(),
  provider: z.string(),
  product_id: z.string(),
  task_id: z.string(),
  currency: z.string(),
  units: numericText,
  provider_cost: numericText,
  billed_cost: numericText,
});

export type RecordUsageFormValues = z.infer<typeof recordUsageSchema>;

export const recordUsageDefaults: RecordUsageFormValues = {
  customer_id: "",
  event_type: "",
  provider: "",
  product_id: "",
  task_id: "",
  currency: "",
  units: "",
  provider_cost: "",
  billed_cost: "",
};

/** Dollar text → integer micros, or undefined when blank. */
export function dollarsToMicros(text: string): number | undefined {
  const t = text.trim();
  if (t === "") return undefined;
  const n = Number(t);
  return Number.isNaN(n) ? undefined : Math.round(n * 1_000_000);
}

/** Numeric text → integer, or undefined when blank. */
export function textToInt(text: string): number | undefined {
  const t = text.trim();
  if (t === "") return undefined;
  const n = Number(t);
  return Number.isNaN(n) ? undefined : Math.round(n);
}

/** Trimmed string, or undefined when blank (so we omit empty optionals). */
export function orUndefined(text: string): string | undefined {
  const t = text.trim();
  return t === "" ? undefined : t;
}
