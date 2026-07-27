import { z } from "zod";
import type { ProgramCreate, ProgramUpdate, RewardType } from "../api/types";

/**
 * All numeric program fields are held as strings in the form so an empty
 * optional cap can be distinguished from a real 0 and omitted from the request.
 * They are parsed to numbers by `toProgramCreate` / `toProgramUpdate`.
 */
const requiredPositive = (msg: string) =>
  z
    .string()
    .trim()
    .min(1, msg)
    .refine((v) => !Number.isNaN(Number(v)) && Number(v) > 0, msg);

const requiredPositiveInt = (msg: string) =>
  z
    .string()
    .trim()
    .min(1, msg)
    .refine((v) => Number.isInteger(Number(v)) && Number(v) >= 1, msg);

const optionalNonNeg = z
  .string()
  .trim()
  .optional()
  .refine(
    (v) => !v || (!Number.isNaN(Number(v)) && Number(v) >= 0),
    "Enter a valid number, or leave blank",
  );

const optionalNonNegInt = z
  .string()
  .trim()
  .optional()
  .refine(
    (v) => !v || (Number.isInteger(Number(v)) && Number(v) >= 0),
    "Enter a whole number, or leave blank",
  );

export const programSchema = z.object({
  reward_type: z.enum(["flat_fee", "revenue_share", "profit_share"]),
  reward_value: requiredPositive("Enter a reward value greater than 0"),
  attribution_window_days: requiredPositiveInt("Enter at least 1 day"),
  reward_window_days: optionalNonNegInt,
  // Dollars in the UI; converted to micros on submit.
  max_reward_dollars: optionalNonNeg,
  estimated_cost_percentage: optionalNonNeg,
  max_referrals_per_day: optionalNonNegInt,
  min_customer_age_hours: optionalNonNegInt,
});

export type ProgramFormValues = z.infer<typeof programSchema>;

const num = (v: string | undefined): number | undefined =>
  v && v.trim() !== "" ? Number(v) : undefined;

const dollarsToMicros = (v: string | undefined): number | undefined =>
  v && v.trim() !== "" ? Math.round(Number(v) * 1_000_000) : undefined;

/** Shared shape of the parsed numeric fields (create & update share these). */
function parseShared(v: ProgramFormValues) {
  return {
    reward_value: Number(v.reward_value),
    attribution_window_days: Number(v.attribution_window_days),
    reward_window_days: num(v.reward_window_days),
    max_reward_micros: dollarsToMicros(v.max_reward_dollars),
    estimated_cost_percentage: num(v.estimated_cost_percentage),
    max_referrals_per_day: num(v.max_referrals_per_day),
    min_customer_age_hours: num(v.min_customer_age_hours),
  };
}

export function toProgramCreate(v: ProgramFormValues): ProgramCreate {
  return { reward_type: v.reward_type, ...parseShared(v) };
}

export function toProgramUpdate(v: ProgramFormValues): ProgramUpdate {
  return { reward_type: v.reward_type, ...parseShared(v) };
}

/** Seed a form from an existing program (numbers → display strings). */
export function programToForm(p: {
  reward_type: string;
  reward_value: number;
  attribution_window_days: number;
  reward_window_days?: number | null;
  max_reward_micros?: number | null;
  estimated_cost_percentage?: number | null;
  max_referrals_per_day?: number | null;
  min_customer_age_hours?: number | null;
}): ProgramFormValues {
  const str = (n: number | null | undefined) =>
    n == null ? "" : String(n);
  return {
    reward_type: (p.reward_type as RewardType) ?? "flat_fee",
    reward_value: String(p.reward_value),
    attribution_window_days: String(p.attribution_window_days),
    reward_window_days: str(p.reward_window_days),
    max_reward_dollars:
      p.max_reward_micros == null ? "" : String(p.max_reward_micros / 1_000_000),
    estimated_cost_percentage: str(p.estimated_cost_percentage),
    max_referrals_per_day: str(p.max_referrals_per_day),
    min_customer_age_hours: str(p.min_customer_age_hours),
  };
}

// --- Referrer registration & attribution ----------------------------------

export const registerReferrerSchema = z.object({
  customer_id: z.string().trim().min(1, "Enter a customer ID"),
});
export type RegisterReferrerValues = z.infer<typeof registerReferrerSchema>;

export const attributeSchema = z
  .object({
    customer_id: z.string().trim().min(1, "Enter the referred customer's ID"),
    code: z.string().trim().optional(),
    link_token: z.string().trim().optional(),
  })
  .refine((v) => Boolean(v.code) || Boolean(v.link_token), {
    message: "Provide a referral code or a link token",
    path: ["code"],
  });
export type AttributeValues = z.infer<typeof attributeSchema>;
