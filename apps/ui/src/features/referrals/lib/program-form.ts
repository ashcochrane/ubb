// Form model for the referral program (create AND edit).
//
// The contract's PATCH body (ProgramUpdateRequest) drops every bound that
// the create body declares — no min/max anywhere, and reward_type loses its
// enum. Per the discovery spec we deliberately COPY the create-time bounds
// here so both forms validate identically; the constants below are the
// create contract's numbers.
//
// ⚠ **THE REWARD IS TWO WIRE FIELDS, EXACTLY ONE SET BY THE TYPE (R10 Stage
// C5, A-3).** `reward_amount_micros` is the flat fee, in micros, for
// `flat_fee`; `reward_share_basis_points` (1..10000, 10000 = the whole) is
// the share for `revenue_share` / `profit_share`. The server refuses the
// other, so the request carries only the one the type names — never both,
// never null for the other. The form keeps ONE entry: currency units for a
// flat fee, a PERCENT for a share (the user types 10 for 10 %, which goes
// out as 1000 basis points), and basis points come back as a percent (÷ 100)
// when editing. A percent exists only in the form; basis points only on the
// wire. The same holds for `estimated_cost_basis_points` (0..10000): entered
// as a percent, sent as basis points.

import { z } from "zod";

import { formatMicros, formatPercentMicros } from "@/lib/format";
import { rewardTypeLabel } from "./referral-vocabulary";

import type {
  ProgramCreateRequest,
  ProgramOut,
  ProgramUpdateRequest,
  RewardType,
} from "../api/types";

export const REWARD_TYPES = ["flat_fee", "revenue_share", "profit_share"] as const;

export function isRewardType(value: string): value is RewardType {
  return (REWARD_TYPES as readonly string[]).includes(value);
}

// Create-time contract bounds.
const REWARD_AMOUNT_MICROS_MAX = 100_000_000_000; // micros for flat_fee → $100,000
const SHARE_BASIS_POINTS = { min: 1, max: 10_000 };
const ESTIMATED_COST_BASIS_POINTS = { min: 0, max: 10_000 };
const MAX_REWARD_MICROS_MAX = 999_999_999_999;
const ATTRIBUTION_DAYS = { min: 1, max: 365 };
const REWARD_WINDOW_DAYS = { min: 1, max: 3650 };
const REFERRALS_PER_DAY = { min: 1, max: 10_000 };
const CUSTOMER_AGE_HOURS = { min: 0, max: 8760 };

/** Currency units → integer micros (the only money conversion in this form). */
export function amountToMicros(amount: number): number {
  return Math.round(amount * 1_000_000);
}

export function microsToAmountInput(micros: number): string {
  return String(micros / 1_000_000);
}

/** A percent entry → basis points: 10 → 1000, 12.5 → 1250. */
export function percentToBasisPoints(percent: number): number {
  return Math.round(percent * 100);
}

/** Basis points → the percent the form shows: 1250 → "12.5". */
export function basisPointsToPercentInput(basisPoints: number): string {
  return String(basisPoints / 100);
}

/**
 * Basis points as a percent, worded: 1000 → "10%", 1250 → "12.5%". A
 * percent in micros is how `@/lib/format` renders one exactly, and one basis
 * point is ten thousand of those.
 */
export function basisPointsPercentLabel(basisPoints: number): string {
  return formatPercentMicros(basisPoints * 10_000);
}

/** One basis point is the finest the wire takes: at most two decimal places. */
function isWholeBasisPoints(percent: number): boolean {
  return Math.abs(percent * 100 - Math.round(percent * 100)) < 1e-6;
}

/** "" → null (unset); non-numeric → NaN (invalid); otherwise the number. */
function parseInput(raw: string): number | null {
  const trimmed = raw.trim();
  if (trimmed === "") return null;
  const value = Number(trimmed);
  return Number.isFinite(value) ? value : Number.NaN;
}

const isInt = (value: number, min: number, max: number) =>
  Number.isInteger(value) && value >= min && value <= max;

export const programFormSchema = z
  .object({
    reward_type: z.enum(REWARD_TYPES),
    /** Currency units for a flat fee; a PERCENT for a share. */
    reward_amount: z.string(),
    attribution_window_days: z.string(),
    reward_window_days: z.string(),
    max_reward: z.string(),
    /** A PERCENT; sent as basis points. */
    estimated_cost_percent: z.string(),
    max_referrals_per_day: z.string(),
    min_customer_age_hours: z.string(),
  })
  .superRefine((values, ctx) => {
    const fail = (path: string, message: string) =>
      ctx.addIssue({ code: "custom", path: [path], message });

    const reward = parseInput(values.reward_amount);
    if (reward === null) {
      fail(
        "reward_amount",
        values.reward_type === "flat_fee" ? "Enter a reward amount" : "Enter a reward percentage",
      );
    } else if (Number.isNaN(reward) || reward <= 0) {
      fail("reward_amount", "Enter a number greater than zero");
    } else if (values.reward_type === "flat_fee") {
      if (amountToMicros(reward) > REWARD_AMOUNT_MICROS_MAX) {
        fail("reward_amount", "At most 100,000 (in currency units) per referral");
      }
    } else if (!isWholeBasisPoints(reward)) {
      fail("reward_amount", "At most two decimal places (one basis point)");
    } else if (
      !isInt(percentToBasisPoints(reward), SHARE_BASIS_POINTS.min, SHARE_BASIS_POINTS.max)
    ) {
      fail("reward_amount", "Percentage must be between 0.01 and 100");
    }

    const attribution = parseInput(values.attribution_window_days);
    if (attribution === null) {
      fail("attribution_window_days", "Enter the attribution window");
    } else if (!isInt(attribution, ATTRIBUTION_DAYS.min, ATTRIBUTION_DAYS.max)) {
      fail("attribution_window_days", "Whole number of days between 1 and 365");
    }

    const rewardWindow = parseInput(values.reward_window_days);
    if (rewardWindow !== null && !isInt(rewardWindow, REWARD_WINDOW_DAYS.min, REWARD_WINDOW_DAYS.max)) {
      fail("reward_window_days", "Whole number of days between 1 and 3,650");
    }

    const maxReward = parseInput(values.max_reward);
    if (maxReward !== null) {
      if (Number.isNaN(maxReward) || maxReward <= 0) {
        fail("max_reward", "Enter an amount greater than zero");
      } else if (amountToMicros(maxReward) > MAX_REWARD_MICROS_MAX) {
        fail("max_reward", "At most 999,999 in currency units");
      }
    }

    const estimatedCost = parseInput(values.estimated_cost_percent);
    if (estimatedCost !== null) {
      if (Number.isNaN(estimatedCost)) {
        fail("estimated_cost_percent", "Percentage between 0 and 100");
      } else if (!isWholeBasisPoints(estimatedCost)) {
        fail("estimated_cost_percent", "At most two decimal places (one basis point)");
      } else if (
        !isInt(
          percentToBasisPoints(estimatedCost),
          ESTIMATED_COST_BASIS_POINTS.min,
          ESTIMATED_COST_BASIS_POINTS.max,
        )
      ) {
        fail("estimated_cost_percent", "Percentage between 0 and 100");
      }
    }

    const perDay = parseInput(values.max_referrals_per_day);
    if (perDay !== null && !isInt(perDay, REFERRALS_PER_DAY.min, REFERRALS_PER_DAY.max)) {
      fail("max_referrals_per_day", "Whole number between 1 and 10,000");
    }

    const minAge = parseInput(values.min_customer_age_hours);
    if (minAge !== null && !isInt(minAge, CUSTOMER_AGE_HOURS.min, CUSTOMER_AGE_HOURS.max)) {
      fail("min_customer_age_hours", "Whole number of hours between 0 and 8,760");
    }
  });

export type ProgramFormValues = z.infer<typeof programFormSchema>;

export function emptyProgramFormValues(): ProgramFormValues {
  return {
    reward_type: "revenue_share",
    reward_amount: "",
    attribution_window_days: "30",
    reward_window_days: "",
    max_reward: "",
    estimated_cost_percent: "",
    max_referrals_per_day: "",
    min_customer_age_hours: "",
  };
}

/**
 * The one reward figure the type names, and no other key: a flat fee goes
 * out as micros, a share as basis points, and the server refuses the one
 * the type does not take.
 */
function rewardFieldsFrom(
  values: ProgramFormValues,
): Pick<ProgramCreateRequest, "reward_amount_micros" | "reward_share_basis_points"> {
  const entered = parseInput(values.reward_amount) ?? 0;
  return values.reward_type === "flat_fee"
    ? { reward_amount_micros: amountToMicros(entered) }
    : { reward_share_basis_points: percentToBasisPoints(entered) };
}

function intOrNull(raw: string): number | null {
  const value = parseInput(raw);
  return value === null || Number.isNaN(value) ? null : Math.round(value);
}

function microsOrNull(raw: string): number | null {
  const value = parseInput(raw);
  return value === null || Number.isNaN(value) ? null : amountToMicros(value);
}

function basisPointsOrNull(raw: string): number | null {
  const value = parseInput(raw);
  return value === null || Number.isNaN(value) ? null : percentToBasisPoints(value);
}

export function toProgramCreateRequest(values: ProgramFormValues): ProgramCreateRequest {
  return {
    reward_type: values.reward_type,
    ...rewardFieldsFrom(values),
    attribution_window_days: intOrNull(values.attribution_window_days) ?? 30,
    reward_window_days: intOrNull(values.reward_window_days),
    max_reward_micros: microsOrNull(values.max_reward),
    estimated_cost_basis_points: basisPointsOrNull(values.estimated_cost_percent),
    max_referrals_per_day: intOrNull(values.max_referrals_per_day),
    min_customer_age_hours: intOrNull(values.min_customer_age_hours),
  };
}

/**
 * The edit dialog is what-you-see-is-what-you-save: the full form state is
 * always sent, with `null` for cleared optional fields (intent: clear) — and
 * still only the one reward figure the type names.
 */
export function toProgramUpdateRequest(values: ProgramFormValues): ProgramUpdateRequest {
  return {
    reward_type: values.reward_type,
    ...rewardFieldsFrom(values),
    attribution_window_days: intOrNull(values.attribution_window_days) ?? 30,
    reward_window_days: intOrNull(values.reward_window_days),
    max_reward_micros: microsOrNull(values.max_reward),
    estimated_cost_basis_points: basisPointsOrNull(values.estimated_cost_percent),
    max_referrals_per_day: intOrNull(values.max_referrals_per_day),
    min_customer_age_hours: intOrNull(values.min_customer_age_hours),
  };
}

export function programToFormValues(program: ProgramOut): ProgramFormValues {
  // reward_type is an open string on the way OUT — narrow it, fall back to
  // revenue_share for unknown future values.
  const rewardType = isRewardType(program.reward_type) ? program.reward_type : "revenue_share";
  return {
    reward_type: rewardType,
    reward_amount:
      rewardType === "flat_fee"
        ? program.reward_amount_micros === null
          ? ""
          : microsToAmountInput(program.reward_amount_micros)
        : program.reward_share_basis_points === null
          ? ""
          : basisPointsToPercentInput(program.reward_share_basis_points),
    attribution_window_days: String(program.attribution_window_days),
    reward_window_days:
      program.reward_window_days === null ? "" : String(program.reward_window_days),
    max_reward:
      program.max_reward_micros === null ? "" : microsToAmountInput(program.max_reward_micros),
    estimated_cost_percent:
      program.estimated_cost_basis_points === null
        ? ""
        : basisPointsToPercentInput(program.estimated_cost_basis_points),
    max_referrals_per_day:
      program.max_referrals_per_day === null ? "" : String(program.max_referrals_per_day),
    min_customer_age_hours:
      program.min_customer_age_hours === null ? "" : String(program.min_customer_age_hours),
  };
}

/** "10% of referred revenue" / "$5.00 per referral" — for the settings list. */
export function rewardSummary(
  program: Pick<ProgramOut, "reward_type" | "reward_amount_micros" | "reward_share_basis_points">,
  currency: string,
): string {
  const { reward_type: rewardType } = program;
  if (rewardType === "flat_fee" && program.reward_amount_micros !== null) {
    return `${formatMicros(program.reward_amount_micros, currency)} per referral`;
  }
  if (program.reward_share_basis_points !== null) {
    const share = basisPointsPercentLabel(program.reward_share_basis_points);
    if (rewardType === "revenue_share") return `${share} of referred revenue`;
    if (rewardType === "profit_share") return `${share} of referred profit`;
  }
  return rewardTypeLabel(rewardType);
}
