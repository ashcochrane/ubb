// Pure helpers + zod schemas for the billing feature's forms.

import { z } from "zod";

import type { BudgetConfig, BudgetConfigIn, PostpaidConfig, PostpaidConfigIn } from "../api/types";

// ---------------------------------------------------------------------------
// Money conversion — inputs are typed in currency units, the API takes micros.

/** "25.50" → 25_500_000. Returns NaN for unparseable input. */
export function currencyToMicros(value: string): number {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return NaN;
  return Math.round(amount * 1_000_000);
}

/**
 * 2_500_000_000 → "2500", 2_500_500 → "2.5005" (for prefilling currency
 * inputs). Full precision, never rounded: the budget PUT is a FULL upsert,
 * so an untouched prefill must round-trip through currencyToMicros to the
 * exact stored micros.
 */
export function microsToCurrencyInput(micros: number): string {
  return (micros / 1_000_000).toString();
}

const currencyAmountField = (opts: { min: number }) =>
  z
    .string()
    .min(1, "Required")
    .refine((v) => Number.isFinite(Number(v)), "Enter a number")
    .refine((v) => Number(v) >= opts.min, `Must be at least ${opts.min}`)
    // The API caps amount_micros at 999,999,999,999 (≈ 999,999 currency units).
    .refine((v) => currencyToMicros(v) <= 999_999_999_999, "Amount is too large");

// ---------------------------------------------------------------------------
// Tenant budget — PUT is a FULL upsert.

export const budgetFormSchema = z.object({
  cap: currencyAmountField({ min: 0 }),
  enforce_mode: z.enum(["alert_only", "blocking"]),
  hard_stop_pct: z
    .string()
    .min(1, "Required")
    .refine((v) => /^\d+$/.test(v), "Whole number")
    .refine((v) => Number(v) >= 1 && Number(v) <= 1000, "Between 1 and 1000"),
  alert_levels: z.array(z.number().int().min(1).max(1000)),
  fail_closed: z.boolean(),
});

export type BudgetFormValues = z.infer<typeof budgetFormSchema>;

/**
 * `BudgetConfigOut.enforce_mode` is an open string (ADR-003) — the PUT side
 * constrains it to these two values, but GET never guarantees the stored
 * value is one of them. Unrecognized values fall back to the non-blocking
 * mode rather than silently editing a config as more restrictive than it is.
 */
function narrowEnforceMode(value: string): "alert_only" | "blocking" {
  return value === "blocking" ? "blocking" : "alert_only";
}

export function budgetToFormValues(budget: BudgetConfig): BudgetFormValues {
  return {
    cap: microsToCurrencyInput(budget.cap_micros),
    enforce_mode: narrowEnforceMode(budget.enforce_mode),
    hard_stop_pct: String(budget.hard_stop_pct),
    alert_levels: [...budget.alert_levels].sort((a, b) => a - b),
    fail_closed: budget.fail_closed,
  };
}

/** Full-upsert body: every field is always present. */
export function budgetFormToPayload(values: BudgetFormValues): BudgetConfigIn {
  return {
    cap_micros: currencyToMicros(values.cap),
    enforce_mode: values.enforce_mode,
    hard_stop_pct: Number(values.hard_stop_pct),
    alert_levels: values.alert_levels,
    fail_closed: values.fail_closed,
  };
}

// ---------------------------------------------------------------------------
// Postpaid config — PUT is PARTIAL: omitted preserves, explicit "" clears.

export type GroupByMode = "single" | "product" | "tag";

export interface PostpaidFormState {
  mode: GroupByMode;
  tagKey: string;
  consolidate: boolean;
}

export function postpaidToFormState(config: PostpaidConfig): PostpaidFormState {
  const groupBy = config.usage_line_item_group_by;
  if (groupBy.startsWith("tag:")) {
    return {
      mode: "tag",
      tagKey: groupBy.slice("tag:".length),
      consolidate: config.consolidate_with_subscription,
    };
  }
  if (groupBy === "product_id") {
    return { mode: "product", tagKey: "", consolidate: config.consolidate_with_subscription };
  }
  return { mode: "single", tagKey: "", consolidate: config.consolidate_with_subscription };
}

export function groupByValue(mode: GroupByMode, tagKey: string): string {
  if (mode === "product") return "product_id";
  if (mode === "tag") return `tag:${tagKey.trim()}`;
  return "";
}

/**
 * Build the PARTIAL update body: only fields that differ from the currently
 * stored config are included (omitted = preserved server-side; "" is sent
 * explicitly to clear grouping). Returns null when nothing changed.
 */
export function buildPostpaidPayload(
  current: PostpaidConfig,
  next: PostpaidFormState,
): PostpaidConfigIn | null {
  const payload: PostpaidConfigIn = {};
  const nextGroupBy = groupByValue(next.mode, next.tagKey);
  if (nextGroupBy !== current.usage_line_item_group_by) {
    payload.usage_line_item_group_by = nextGroupBy;
  }
  if (next.consolidate !== current.consolidate_with_subscription) {
    payload.consolidate_with_subscription = next.consolidate;
  }
  return Object.keys(payload).length > 0 ? payload : null;
}

// ---------------------------------------------------------------------------
// Manual ledger adjustments (credit / debit).

export const creditFormSchema = z.object({
  customer_id: z.string().min(1, "Required").max(255),
  amount: currencyAmountField({ min: 0 }).refine((v) => Number(v) > 0, "Must be more than 0"),
  reference: z.string().min(1, "Required").max(500),
  source: z.string().min(1, "Required").max(255),
  actor: z.string().max(255),
  reason_code: z.string().max(32),
});

export type CreditFormValues = z.infer<typeof creditFormSchema>;

export const debitFormSchema = z.object({
  customer_id: z.string().min(1, "Required").max(255),
  amount: currencyAmountField({ min: 0 }).refine((v) => Number(v) > 0, "Must be more than 0"),
  reference: z.string().min(1, "Required").max(500),
  actor: z.string().max(255),
  reason_code: z.string().max(32),
  allow_negative: z.boolean(),
});

export type DebitFormValues = z.infer<typeof debitFormSchema>;

// ---------------------------------------------------------------------------
// Usage-invoice period filter — <input type="month"> gives "2026-07"; the API
// filter is the period-start date.

export function monthToPeriodDate(month: string): string | undefined {
  if (!/^\d{4}-\d{2}$/.test(month)) return undefined;
  return `${month}-01`;
}
