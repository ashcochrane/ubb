// Zod schemas for the feature's forms. Money fields stay STRINGS in the form
// (entered in currency units) and are converted to integer micros at submit
// via toMicros — never float math on stored money.

import { z } from "zod";

import {
  RECOGNITION_METHOD_VALUES,
  SPEND_POOL_ENFORCE_MODE_VALUES,
} from "@/lib/vocabulary";

import { suppliedPeriod } from "./helpers";

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

/** The pool's declaration; the mode is the registry's closed pair, held by reference. */
export const customerSpendPoolSchema = z.object({
  cap: nonNegativeMoney,
  enforce_mode: z.enum(SPEND_POOL_ENFORCE_MODE_VALUES),
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
export type CustomerSpendPoolForm = z.infer<typeof customerSpendPoolSchema>;

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

// NO RECURRING REVENUE FORM (#496). It validated one amount, an interval and
// an open-ended span for a record that had no periods and no source reference
// - and the interval it made the tenant choose was never read by anything
// that computed a number. Its replacement is directly below.

/**
 * What a tenant states it earned from one customer over one period (#508).
 *
 * ⚠ **THE AMOUNT MAY BE ZERO AND THAT IS A STATEMENT, NOT AN EMPTY FIELD.**
 * #153 section 3.4 rules a deliberate zero one of the four revenue states -
 * a free month, which produces a real negative margin against known cost - and
 * it is a different fact from having supplied nothing at all, which is served
 * as an absence rather than a figure. A schema demanding "greater than zero"
 * would make the free month unsayable on the only surface that says it.
 *
 * ⚠ **AND THE SPAN IS NOT TWO DATE FIELDS.** The tenant names the MONTH and,
 * where the customer began part-way through it, the DAY they began; the span
 * is derived by `suppliedPeriod`. That is the mid-period affordance section 9
 * rules into this slice, and the reason it is here rather than in the
 * component is that a refusal has to be able to say which field to change.
 */
export const suppliedRevenueSchema = z
  .object({
    amount: nonNegativeMoney,
    /** `<input type="month">` gives "2026-06". */
    month: z.string().trim().min(1, "Choose the month this covers"),
    /** "" = the whole month; otherwise the day the customer began. */
    began_on: z.string().trim(),
    // The registry's closed pair, held BY REFERENCE — so a third method is a
    // `tsc` failure at the radio list rather than a value the form can never
    // send.
    recognition_method: z.enum(RECOGNITION_METHOD_VALUES),
    source_reference: z
      .string()
      .trim()
      .min(1, "Say where this number came from")
      .max(255, "255 characters max"),
  })
  .superRefine((value, ctx) => {
    if (suppliedPeriod(value.month, value.began_on) === null) {
      ctx.addIssue({
        code: "custom",
        // The month is valid on its own in the case that actually happens -
        // a day picked before the month was changed - so the refusal names
        // the day, which is the field that has to move.
        path: value.began_on === "" ? ["month"] : ["began_on"],
        message:
          value.began_on === ""
            ? "Choose the month this covers"
            : "Pick a day inside the month this covers",
      });
    }
  });
export type SuppliedRevenueForm = z.infer<typeof suppliedRevenueSchema>;

// ⚠ NO MARKUP FORM (#369). It validated a percentage beside a flat per-event
// amount for the customer override dialog, and both the dialog and the record
// behind it are deleted. The rung that replaced the tenant half takes ONE term
// — a margin over cost never composes with an addend — so the two-field shape
// was wrong for the surface that replaced it as well as unused here. That
// surface arrived in #372 and it is a RULE editor rather than a number field:
// what one customer is charged is a whole rule, method included, and it is
// stated in `features/pricing/lib/schemas.ts`.

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
