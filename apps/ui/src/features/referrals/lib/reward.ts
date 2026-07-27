import { formatDollars, formatPercent } from "@/lib/format";
import type { RewardType } from "../api/types";

/**
 * Render a program's `reward_value` in the units its reward model implies:
 * flat_fee is a per-referral dollar amount; the two share models are percents.
 */
export function formatRewardValue(
  rewardType: string,
  value: number,
): string {
  return rewardType === "flat_fee"
    ? formatDollars(value)
    : formatPercent(value);
}

/** Human hint describing what `reward_value` means for a reward type. */
export function rewardValueHint(rewardType: RewardType): string {
  switch (rewardType) {
    case "flat_fee":
      return "Fixed dollar amount paid per successful referral.";
    case "revenue_share":
      return "Percent of the referred customer's billed spend.";
    case "profit_share":
      return "Percent of the margin earned on the referred customer.";
  }
}

/** Label for the reward_value input given the reward type. */
export function rewardValueLabel(rewardType: RewardType): string {
  return rewardType === "flat_fee"
    ? "Reward amount (USD per referral)"
    : "Reward percentage (%)";
}
