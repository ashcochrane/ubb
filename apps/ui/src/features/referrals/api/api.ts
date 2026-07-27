import { referralsApi } from "@/api/client";
import { requireData } from "@/api/errors";
import type { CursorPage } from "@/lib/use-cursor-list";
import type {
  AnalyticsEarnings,
  AnalyticsSummary,
  AttributeReferral,
  AttributeResult,
  Earnings,
  LedgerEntry,
  PayoutExport,
  Program,
  ProgramCreate,
  ProgramUpdate,
  Referral,
  Referrer,
  RegisterReferrer,
} from "./types";

// --- Program ---------------------------------------------------------------

export function getProgram(): Promise<Program> {
  return referralsApi
    .GET("/program")
    .then((r) => requireData(r, "Failed to load referral program"));
}

export function createProgram(body: ProgramCreate): Promise<Program> {
  return referralsApi
    .POST("/program", { body })
    .then((r) => requireData(r, "Failed to create referral program"));
}

export function updateProgram(body: ProgramUpdate): Promise<Program> {
  return referralsApi
    .PATCH("/program", { body })
    .then((r) => requireData(r, "Failed to update referral program"));
}

export function deactivateProgram() {
  return referralsApi
    .DELETE("/program")
    .then((r) => requireData(r, "Failed to deactivate program"));
}

export function reactivateProgram(): Promise<Program> {
  return referralsApi
    .POST("/program/reactivate")
    .then((r) => requireData(r, "Failed to reactivate program"));
}

// --- Referrers -------------------------------------------------------------

export function listReferrers(params?: {
  cursor?: string;
  limit?: number;
}): Promise<CursorPage<Referrer>> {
  return referralsApi
    .GET("/referrers", { params: { query: params } })
    .then((r) => requireData(r, "Failed to load referrers"));
}

export function registerReferrer(body: RegisterReferrer): Promise<Referrer> {
  return referralsApi
    .POST("/referrers", { body })
    .then((r) => requireData(r, "Failed to register referrer"));
}

export function getReferrer(customerId: string): Promise<Referrer> {
  return referralsApi
    .GET("/referrers/{customer_id}", {
      params: { path: { customer_id: customerId } },
    })
    .then((r) => requireData(r, "Failed to load referrer"));
}

export function getReferrerEarnings(customerId: string): Promise<Earnings> {
  return referralsApi
    .GET("/referrers/{customer_id}/earnings", {
      params: { path: { customer_id: customerId } },
    })
    .then((r) => requireData(r, "Failed to load earnings"));
}

export function listReferrerReferrals(
  customerId: string,
  params?: { cursor?: string; limit?: number },
): Promise<CursorPage<Referral>> {
  return referralsApi
    .GET("/referrers/{customer_id}/referrals", {
      params: { path: { customer_id: customerId }, query: params },
    })
    .then((r) => requireData(r, "Failed to load referrals"));
}

// --- Attribution & referrals ----------------------------------------------

export function attributeReferral(
  body: AttributeReferral,
): Promise<AttributeResult> {
  return referralsApi
    .POST("/attribute", { body })
    .then((r) => requireData(r, "Failed to attribute referral"));
}

export function revokeReferral(referralId: string) {
  return referralsApi
    .DELETE("/referrals/{referral_id}", {
      params: { path: { referral_id: referralId } },
    })
    .then((r) => requireData(r, "Failed to revoke referral"));
}

export function getReferralLedger(
  referralId: string,
  params?: { cursor?: string; limit?: number },
): Promise<CursorPage<LedgerEntry>> {
  return referralsApi
    .GET("/referrals/{referral_id}/ledger", {
      params: { path: { referral_id: referralId }, query: params },
    })
    .then((r) => requireData(r, "Failed to load ledger"));
}

// --- Analytics & payouts ---------------------------------------------------

export function getAnalyticsSummary(): Promise<AnalyticsSummary> {
  return referralsApi
    .GET("/analytics/summary")
    .then((r) => requireData(r, "Failed to load analytics"));
}

export function getAnalyticsEarnings(params?: {
  period_start?: string;
  period_end?: string;
}): Promise<AnalyticsEarnings> {
  return referralsApi
    .GET("/analytics/earnings", { params: { query: params } })
    .then((r) => requireData(r, "Failed to load earnings by period"));
}

export function getPayoutExport(): Promise<PayoutExport> {
  return referralsApi
    .GET("/payouts/export")
    .then((r) => requireData(r, "Failed to load payout export"));
}
