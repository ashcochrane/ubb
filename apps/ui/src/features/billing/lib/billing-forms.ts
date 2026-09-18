// Pure helpers + zod schemas for the billing feature's forms. The seat-default
// pool's form is `./customer-spend-pool-form` (#468, split out before anything
// here was renamed — spec §20).

import { z } from "zod";

import type { PostpaidConfig, PostpaidConfigIn } from "../api/types";

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
 * inputs). Full precision, never rounded: the pool PUT is a FULL upsert,
 * so an untouched prefill must round-trip through currencyToMicros to the
 * exact stored micros.
 */
export function microsToCurrencyInput(micros: number): string {
  return (micros / 1_000_000).toString();
}

export const currencyAmountField = (opts: { min: number }) =>
  z
    .string()
    .min(1, "Required")
    .refine((v) => Number.isFinite(Number(v)), "Enter a number")
    .refine((v) => Number(v) >= opts.min, `Must be at least ${opts.min}`)
    // The API caps amount_micros at 999,999,999,999 (≈ 999,999 currency units).
    .refine((v) => currencyToMicros(v) <= 999_999_999_999, "Amount is too large");

// ---------------------------------------------------------------------------
// Postpaid config — PUT is PARTIAL: omitted preserves, explicit "" clears.

// ⚠ **THE MODE, THE FREE-TEXT KEY AND THE BUILDER BETWEEN THEM ARE GONE
// (#508, slice 7 §11).** The form used to offer three shapes — one total, one
// line per product, one line per value of a key the tenant TYPED — and compose
// a stored string out of them. ADR-0005 calls that key the sharpest of the
// three free-text hatches and the only one a paying customer reads: *"an
// unbounded free-text key driving invoice line labels is how a 5,000-line
// invoice happens."* What replaces it is one word of the SAME grouping
// vocabulary the analytics surfaces use, chosen from the tenant's own
// discovery contract, which the server validates before it stores (#503).
//
// So there is nothing to compose. The state IS the request word, and the two
// functions below only decide what has changed.

export interface PostpaidFormState {
  /**
   * The axis's own request word — `field:<name>` or `rollup:<name>` — or the
   * empty string for a single line carrying one total.
   *
   * The empty string is an ABSENCE of grouping rather than a mode meaning
   * "don't group": there is no axis that produces one line, so the way to ask
   * for one is to name no axis.
   */
  axis: string;
  consolidate: boolean;
}

export function postpaidToFormState(config: PostpaidConfig): PostpaidFormState {
  return {
    axis: config.group_by,
    consolidate: config.consolidate_with_subscription,
  };
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
  if (next.axis !== current.group_by) {
    payload.group_by = next.axis;
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
