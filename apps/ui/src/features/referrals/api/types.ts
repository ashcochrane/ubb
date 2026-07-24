// Type aliases from the generated contract (ADR-002: openapi/v1.json is the
// single source of truth). Every response this feature consumes is fully
// typed by a named component schema — the referrals slice has NO untyped
// (additionalProperties) responses, so no local narrowing interfaces exist.

import type { MarginSchemas, ReferralSchemas } from "@/api/types";

export type ProgramOut = ReferralSchemas["ProgramOut"];
export type ProgramCreateRequest = ReferralSchemas["ProgramCreateRequest"];
export type ProgramUpdateRequest = ReferralSchemas["ProgramUpdateRequest"];

/** The ONE closed enum in the whole contract (create input only). */
export type RewardType = ProgramCreateRequest["reward_type"];

export type ReferrerOut = ReferralSchemas["ReferrerOut"];
export type ReferralOut = ReferralSchemas["ReferralOut"];
export type LedgerEntryOut = ReferralSchemas["LedgerEntryOut"];
export type EarningsOut = ReferralSchemas["EarningsOut"];

export type AnalyticsSummaryOut = ReferralSchemas["AnalyticsSummaryOut"];
export type AnalyticsEarningsOut = ReferralSchemas["AnalyticsEarningsOut"];
export type ReferrerEarningsSummary = ReferralSchemas["ReferrerEarningsSummary"];

export type PayoutExportOut = ReferralSchemas["PayoutExportOut"];
export type PayoutRow = ReferralSchemas["PayoutRow"];

export type AttributeRequest = ReferralSchemas["AttributeRequest"];
export type AttributeResponse = ReferralSchemas["AttributeResponse"];
export type StatusResponse = ReferralSchemas["StatusResponse"];

/** Row of GET /margin/customers — used only to feed the customer picker. */
export type MarginCustomerRow = MarginSchemas["CustomerMarginListRow"];

/** Query params for GET /referrals/analytics/earnings. */
export interface EarningsPeriodParams {
  period_start?: string;
  period_end?: string;
}
