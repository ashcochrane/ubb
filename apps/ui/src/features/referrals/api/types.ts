import type { ReferralSchemas } from "@/api/types";

export type Program = ReferralSchemas["ProgramOut"];
export type ProgramCreate = ReferralSchemas["ProgramCreateRequest"];
export type ProgramUpdate = ReferralSchemas["ProgramUpdateRequest"];
export type RewardType = ProgramCreate["reward_type"];

export type Referrer = ReferralSchemas["ReferrerOut"];
export type RegisterReferrer = ReferralSchemas["RegisterReferrerRequest"];
export type Earnings = ReferralSchemas["EarningsOut"];
export type Referral = ReferralSchemas["ReferralOut"];

export type AttributeReferral = ReferralSchemas["AttributeRequest"];
export type AttributeResult = ReferralSchemas["AttributeResponse"];

export type LedgerEntry = ReferralSchemas["LedgerEntryOut"];

export type AnalyticsSummary = ReferralSchemas["AnalyticsSummaryOut"];
export type AnalyticsEarnings = ReferralSchemas["AnalyticsEarningsOut"];
export type ReferrerEarningsSummary = ReferralSchemas["ReferrerEarningsSummary"];
export type PayoutExport = ReferralSchemas["PayoutExportOut"];
export type PayoutRow = ReferralSchemas["PayoutRow"];

/** The three reward models a program can run on. */
export const REWARD_TYPES: readonly RewardType[] = [
  "flat_fee",
  "revenue_share",
  "profit_share",
];
