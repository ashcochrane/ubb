// Real API calls for the referrals surface. Every call goes through
// `unwrap` so callers always reject with a typed ApiProblem — most referral
// operations declare only their 200 in the schema, and runtime errors still
// arrive as problem+json.

import { meteringApi, referralsApi } from "@/api/client";
import type { CursorPage } from "@/api/pagination";
import { unwrap } from "@/api/problem";
import {
  customerIdsIn,
  FIELD_AXIS,
  SUPPLIER_COGS,
} from "@/lib/economic-query";


import type {
  AnalyticsEarningsOut,
  AnalyticsSummaryOut,
  AttributeRequest,
  AttributeResponse,
  EarningsOut,
  EarningsPeriodParams,
  LedgerEntryOut,
  CustomerChoice,
  PayoutExportOut,
  ProgramCreateRequest,
  ProgramOut,
  ProgramUpdateRequest,
  ReferralOut,
  ReferrerOut,
  StatusResponse,
} from "./types";

const LIST_LIMIT = 50;

// --- Program -----------------------------------------------------------------

export async function getProgram(): Promise<ProgramOut> {
  return unwrap(await referralsApi.GET("/program"));
}

export async function createProgram(body: ProgramCreateRequest): Promise<ProgramOut> {
  return unwrap(await referralsApi.POST("/program", { body }));
}

export async function updateProgram(body: ProgramUpdateRequest): Promise<ProgramOut> {
  return unwrap(await referralsApi.PATCH("/program", { body }));
}

export async function deactivateProgram(): Promise<StatusResponse> {
  return unwrap(await referralsApi.DELETE("/program"));
}

export async function reactivateProgram(): Promise<ProgramOut> {
  return unwrap(await referralsApi.POST("/program/reactivate"));
}

// --- Analytics & payouts -----------------------------------------------------

export async function getAnalyticsSummary(): Promise<AnalyticsSummaryOut> {
  return unwrap(await referralsApi.GET("/analytics/summary"));
}

export async function getAnalyticsEarnings(
  params: EarningsPeriodParams,
): Promise<AnalyticsEarningsOut> {
  return unwrap(
    await referralsApi.GET("/analytics/earnings", { params: { query: params } }),
  );
}

export async function getPayoutExport(): Promise<PayoutExportOut> {
  return unwrap(await referralsApi.GET("/payouts/export"));
}

// --- Referrers ---------------------------------------------------------------

export async function listReferrers(cursor?: string): Promise<CursorPage<ReferrerOut>> {
  return unwrap(
    await referralsApi.GET("/referrers", {
      params: { query: { cursor, limit: LIST_LIMIT } },
    }),
  );
}

export async function registerReferrer(customerId: string): Promise<ReferrerOut> {
  return unwrap(
    await referralsApi.POST("/referrers", { body: { customer_id: customerId } }),
  );
}

export async function getReferrer(customerId: string): Promise<ReferrerOut> {
  return unwrap(
    await referralsApi.GET("/referrers/{customer_id}", {
      params: { path: { customer_id: customerId } },
    }),
  );
}

export async function getReferrerEarnings(customerId: string): Promise<EarningsOut> {
  return unwrap(
    await referralsApi.GET("/referrers/{customer_id}/earnings", {
      params: { path: { customer_id: customerId } },
    }),
  );
}

export async function listReferrerReferrals(
  customerId: string,
  cursor?: string,
): Promise<CursorPage<ReferralOut>> {
  return unwrap(
    await referralsApi.GET("/referrers/{customer_id}/referrals", {
      params: { path: { customer_id: customerId }, query: { cursor, limit: LIST_LIMIT } },
    }),
  );
}

// --- Individual referrals ----------------------------------------------------

export async function attributeReferral(body: AttributeRequest): Promise<AttributeResponse> {
  return unwrap(await referralsApi.POST("/attribute", { body }));
}

export async function revokeReferral(referralId: string): Promise<StatusResponse> {
  // NOTE the doubled segment: the full path is /api/v1/referrals/referrals/{id}.
  return unwrap(
    await referralsApi.DELETE("/referrals/{referral_id}", {
      params: { path: { referral_id: referralId } },
    }),
  );
}

export async function getReferralLedger(
  referralId: string,
  cursor?: string,
): Promise<CursorPage<LedgerEntryOut>> {
  return unwrap(
    await referralsApi.GET("/referrals/{referral_id}/ledger", {
      params: { path: { referral_id: referralId }, query: { cursor, limit: LIST_LIMIT } },
    }),
  );
}

// --- Customer picker (margin namespace) --------------------------------------

/**
 * Feed for the "register referrer" customer picker. The read may be
 * unavailable (metering product off) — callers must tolerate failure and fall
 * back to the free UUID input.
 */
export async function listCustomerChoices(): Promise<CustomerChoice[]> {
  const answer = unwrap(
    await meteringApi.GET("/analytics/economics", {
      params: {
        query: { measures: [SUPPLIER_COGS], group_by: [FIELD_AXIS("customer")] },
      },
    }),
  );
  return customerIdsIn(answer).map((customer_id) => ({ customer_id }));
}
