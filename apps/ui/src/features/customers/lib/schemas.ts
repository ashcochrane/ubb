// Zod schemas for the feature's forms. Money fields stay STRINGS in the form
// (entered in currency units) and are converted to integer micros at submit
// via toMicros — never float math on stored money.

import { z } from "zod";

const isFiniteNumber = (value: string) => Number.isFinite(Number(value));

/** Required money amount, strictly positive (currency units). */
export const moneyAmount = z
  .string()
  .trim()
  .min(1, "Enter an amount")
  .refine(isFiniteNumber, "Enter a number")
  .refine((value) => Number(value) > 0, "Enter an amount greater than zero");

/** Optional money amount; empty string = unset. Negative values allowed
 * (only the wind-down floor's wire value may legitimately be negative). */
export const optionalMoney = z
  .string()
  .trim()
  .refine((value) => value === "" || isFiniteNumber(value), "Enter a number");

/** Optional non-negative amount; empty string = unset (inherit). */
export const optionalNonNegativeMoney = z
  .string()
  .trim()
  .refine((value) => value === "" || isFiniteNumber(value), "Enter a number")
  .refine((value) => value === "" || Number(value) >= 0, "Must be zero or more");

/** Non-negative money amount (zero allowed). */
export const nonNegativeMoney = z
  .string()
  .trim()
  .min(1, "Enter an amount")
  .refine(isFiniteNumber, "Enter a number")
  .refine((value) => Number(value) >= 0, "Must be zero or more");

const optionalPositiveInt = z
  .string()
  .trim()
  .refine(
    (value) => value === "" || (Number.isInteger(Number(value)) && Number(value) > 0),
    "Enter a whole number above zero",
  );

// ---------------------------------------------------------------------------

export const createCustomerSchema = z.object({
  external_id: z
    .string()
    .trim()
    .min(1, "External ID is required")
    .max(255, "255 characters max"),
  account_type: z.string().min(1, "Choose an account type"),
  billing_topology: z.string(),
  parent_external_id: z.string().trim(),
  stripe_customer_id: z.string().trim(),
  metadata: z.array(
    z.object({ key: z.string().trim(), value: z.string() }),
  ),
});
export type CreateCustomerForm = z.infer<typeof createCustomerSchema>;

export const topUpSchema = z.object({ amount: moneyAmount });
export type TopUpForm = z.infer<typeof topUpSchema>;

export const withdrawSchema = z.object({
  amount: moneyAmount,
  description: z.string(),
});
export type WithdrawForm = z.infer<typeof withdrawSchema>;

/** One shared form shape for manual credit AND debit; `source` is only
 * required (and only sent) for credits, `allow_negative` only for debits. */
export function adjustSchema(direction: "credit" | "debit") {
  return z.object({
    amount: moneyAmount,
    reference: z.string().trim().min(1, "Reference is required").max(500),
    source:
      direction === "credit"
        ? z.string().trim().min(1, "Source is required").max(255)
        : z.string().trim().max(255),
    reason_code: z.string().trim().max(32, "32 characters max"),
    allow_negative: z.boolean(),
  });
}
export type AdjustForm = z.infer<ReturnType<typeof adjustSchema>>;

/** Grant expiry: the mode radio makes expires_at XOR expires_in_days structural. */
export const grantSchema = z
  .object({
    amount: moneyAmount,
    kind: z.string().min(1, "Choose a kind"),
    expiry_mode: z.enum(["none", "at", "days"]),
    expires_at: z.string().trim(),
    expires_in_days: z.string().trim(),
    description: z.string().max(500, "500 characters max"),
  })
  .superRefine((value, ctx) => {
    if (value.expiry_mode === "at" && value.expires_at === "") {
      ctx.addIssue({
        code: "custom",
        path: ["expires_at"],
        message: "Pick an expiry date",
      });
    }
    if (value.expiry_mode === "days") {
      const days = Number(value.expires_in_days);
      if (!Number.isInteger(days) || days <= 0 || days > 3650) {
        ctx.addIssue({
          code: "custom",
          path: ["expires_in_days"],
          message: "Enter 1–3650 days",
        });
      }
    }
  });
export type GrantForm = z.infer<typeof grantSchema>;

export const budgetSchema = z.object({
  cap: nonNegativeMoney,
  enforce_mode: z.enum(["alert_only", "blocking"]),
  hard_stop_pct: z
    .string()
    .trim()
    .min(1, "Required")
    .refine((value) => {
      const pct = Number(value);
      return Number.isInteger(pct) && pct >= 1 && pct <= 1000;
    }, "Enter a whole number 1–1000"),
  alert_levels: z.string(),
  fail_closed: z.boolean(),
});
export type BudgetForm = z.infer<typeof budgetSchema>;

/**
 * Billing-profile floors, entered as RAW WIRE VALUES (contract semantics):
 * - min_balance = allowed overdraft magnitude, ≥ 0 (the stop line sits at
 *   MINUS this value; the server 422s negatives).
 * - soft_min_balance = wind-down wire value (line at MINUS the value, so a
 *   NEGATIVE entry places the wind-down line above zero); must not exceed
 *   the allowed overdraft (server rule: soft ≤ hard).
 */
export const billingProfileSchema = z
  .object({
    min_balance: optionalNonNegativeMoney,
    soft_min_balance: optionalMoney,
    topup_grant_expiry_days: optionalPositiveInt,
  })
  .superRefine((value, ctx) => {
    if (
      value.min_balance !== "" &&
      value.soft_min_balance !== "" &&
      Number(value.soft_min_balance) > Number(value.min_balance)
    ) {
      ctx.addIssue({
        code: "custom",
        path: ["soft_min_balance"],
        message: "Can't exceed the allowed overdraft.",
      });
    }
  });
export type BillingProfileForm = z.infer<typeof billingProfileSchema>;

export const autoTopUpSchema = z.object({
  is_enabled: z.boolean(),
  amount: moneyAmount,
  threshold: nonNegativeMoney,
});
export type AutoTopUpForm = z.infer<typeof autoTopUpSchema>;

export const revenueProfileSchema = z.object({
  amount: nonNegativeMoney,
  interval: z.string().min(1, "Choose an interval"),
  effective_from: z.string().trim(),
  effective_to: z.string().trim(),
});
export type RevenueProfileForm = z.infer<typeof revenueProfileSchema>;

// ⚠ NO MARKUP FORM (#369). It validated a percentage beside a flat per-event
// amount for the customer override dialog, and both the dialog and the record
// behind it are deleted. The rung that replaced the tenant half takes ONE term
// — a margin over cost never composes with an addend — so the two-field shape
// would be wrong for whatever surface #372 builds as well as unused today.

export const subscribeSchema = z.object({
  plan_key: z.string().trim().min(1, "Plan key is required").max(64),
  seats: z
    .string()
    .trim()
    .refine(
      (value) =>
        value === "" || (Number.isInteger(Number(value)) && Number(value) >= 0),
      "Enter zero or more seats",
    ),
});
export type SubscribeForm = z.infer<typeof subscribeSchema>;

export const seatsSchema = z.object({
  seats: z
    .string()
    .trim()
    .min(1, "Enter a seat count")
    .refine(
      (value) => Number.isInteger(Number(value)) && Number(value) >= 0,
      "Enter zero or more seats",
    ),
});
export type SeatsForm = z.infer<typeof seatsSchema>;

// ⚠ NO `percentToMicros` (#369). Its one caller was the markup override
// dialog. A percentage held in micros is still how the surviving rung carries
// one, and `formatPercentMicros` in `@/lib/format` renders it; the conversion
// the other way belongs with whichever form next takes one.
