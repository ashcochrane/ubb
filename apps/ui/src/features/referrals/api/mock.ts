// Mock provider — same exported signatures as api.ts, backed by the
// module-level state in mock-data.ts so mutations stay coherent within a
// session. Errors are thrown as ApiProblem, exactly like the real client.

import type { CursorPage } from "@/api/pagination";
import { ApiProblem } from "@/api/problem";
import { mockDelay } from "@/lib/api-provider";

import { externalIdFor, mockState } from "./mock-data";
import type {
  AnalyticsEarningsOut,
  AnalyticsSummaryOut,
  AttributeRequest,
  AttributeResponse,
  EarningsOut,
  EarningsPeriodParams,
  LedgerEntryOut,
  MarginCustomerRow,
  PayoutExportOut,
  PayoutRow,
  ProgramCreateRequest,
  ProgramOut,
  ProgramUpdateRequest,
  ReferralOut,
  ReferrerEarningsSummary,
  ReferrerOut,
  StatusResponse,
} from "./types";

function nowIso(): string {
  return new Date().toISOString();
}

function allReferrals(): ReferralOut[] {
  return Object.values(mockState.referralsByReferrer).flat();
}

function notFound(title: string, detail?: string): ApiProblem {
  return new ApiProblem({ status: 404, code: "not_found", title, detail: detail ?? null });
}

// --- Program -----------------------------------------------------------------

export async function getProgram(): Promise<ProgramOut> {
  await mockDelay();
  if (!mockState.program) {
    throw notFound("No referral program", "This workspace hasn't created a referral program yet.");
  }
  return { ...mockState.program };
}

export async function createProgram(body: ProgramCreateRequest): Promise<ProgramOut> {
  await mockDelay();
  if (mockState.program) {
    throw new ApiProblem({
      status: 409,
      code: "conflict",
      title: "Program already exists",
      detail: "This workspace already has a referral program — edit it instead.",
    });
  }
  const now = nowIso();
  mockState.program = {
    id: "prog-new001",
    reward_type: body.reward_type,
    reward_value: body.reward_value,
    attribution_window_days: body.attribution_window_days,
    reward_window_days: body.reward_window_days ?? null,
    max_reward_micros: body.max_reward_micros ?? null,
    estimated_cost_percentage: body.estimated_cost_percentage ?? null,
    max_referrals_per_day: body.max_referrals_per_day ?? null,
    min_customer_age_hours: body.min_customer_age_hours ?? null,
    status: "active",
    created_at: now,
    updated_at: now,
  };
  return { ...mockState.program };
}

export async function updateProgram(body: ProgramUpdateRequest): Promise<ProgramOut> {
  await mockDelay();
  const program = mockState.program;
  if (!program) throw notFound("No referral program");
  if (body.reward_type != null) program.reward_type = body.reward_type;
  if (body.reward_value != null) program.reward_value = body.reward_value;
  if (body.attribution_window_days != null) {
    program.attribution_window_days = body.attribution_window_days;
  }
  if (body.reward_window_days !== undefined) program.reward_window_days = body.reward_window_days;
  if (body.max_reward_micros !== undefined) program.max_reward_micros = body.max_reward_micros;
  if (body.estimated_cost_percentage !== undefined) {
    program.estimated_cost_percentage = body.estimated_cost_percentage;
  }
  if (body.max_referrals_per_day !== undefined) {
    program.max_referrals_per_day = body.max_referrals_per_day;
  }
  if (body.min_customer_age_hours !== undefined) {
    program.min_customer_age_hours = body.min_customer_age_hours;
  }
  program.updated_at = nowIso();
  return { ...program };
}

export async function deactivateProgram(): Promise<StatusResponse> {
  await mockDelay();
  if (!mockState.program) throw notFound("No referral program");
  mockState.program.status = "deactivated";
  mockState.program.updated_at = nowIso();
  return { status: "deactivated" };
}

export async function reactivateProgram(): Promise<ProgramOut> {
  await mockDelay();
  if (!mockState.program) throw notFound("No referral program");
  mockState.program.status = "active";
  mockState.program.updated_at = nowIso();
  return { ...mockState.program };
}

// --- Analytics & payouts -----------------------------------------------------

export async function getAnalyticsSummary(): Promise<AnalyticsSummaryOut> {
  await mockDelay();
  const referrals = allReferrals();
  return {
    total_referrers: mockState.referrers.length,
    total_referrals: referrals.length,
    active_referrals: referrals.filter((r) => r.status === "active").length,
    total_rewards_earned_micros: referrals.reduce((sum, r) => sum + r.total_earned_micros, 0),
    total_referred_spend_micros: referrals.reduce(
      (sum, r) => sum + r.total_referred_spend_micros,
      0,
    ),
  };
}

export async function getAnalyticsEarnings(
  params: EarningsPeriodParams,
): Promise<AnalyticsEarningsOut> {
  await mockDelay();
  const referrers: ReferrerEarningsSummary[] = mockState.referrers
    .map((referrer) => {
      const referrals = mockState.referralsByReferrer[referrer.customer_id] ?? [];
      return {
        referrer_customer_id: referrer.customer_id,
        external_id: externalIdFor(referrer.customer_id),
        referral_code: referrer.referral_code,
        total_earned_micros: referrals.reduce((sum, r) => sum + r.total_earned_micros, 0),
        referral_count: referrals.length,
      };
    })
    .filter((row) => row.referral_count > 0);
  return {
    period_start: params.period_start ?? "2026-07-01",
    period_end: params.period_end ?? "2026-07-24",
    total_earned_micros: referrers.reduce((sum, r) => sum + r.total_earned_micros, 0),
    referrers,
  };
}

export async function getPayoutExport(): Promise<PayoutExportOut> {
  await mockDelay();
  const rows: PayoutRow[] = [];
  for (const referrer of mockState.referrers) {
    const referrals = mockState.referralsByReferrer[referrer.customer_id] ?? [];
    const earned = referrals.reduce((sum, r) => sum + r.total_earned_micros, 0);
    if (earned <= 0) continue;
    rows.push({
      referrer_customer_id: referrer.customer_id,
      external_id: externalIdFor(referrer.customer_id),
      referral_code: referrer.referral_code,
      total_earned_micros: earned,
      total_referred_spend_micros: referrals.reduce(
        (sum, r) => sum + r.total_referred_spend_micros,
        0,
      ),
      referral_count: referrals.length,
      active_referral_count: referrals.filter((r) => r.status === "active").length,
    });
  }
  return {
    data: rows,
    total_payout_micros: rows.reduce((sum, r) => sum + r.total_earned_micros, 0),
    referrer_count: rows.length,
    exported_at: nowIso(),
  };
}

// --- Referrers ---------------------------------------------------------------

export async function listReferrers(_cursor?: string): Promise<CursorPage<ReferrerOut>> {
  await mockDelay();
  return { data: mockState.referrers.map((r) => ({ ...r })), has_more: false, next_cursor: null };
}

export async function registerReferrer(customerId: string): Promise<ReferrerOut> {
  await mockDelay();
  if (mockState.referrers.some((r) => r.customer_id === customerId)) {
    throw new ApiProblem({
      status: 409,
      code: "conflict",
      title: "Already a referrer",
      detail: "This customer is already registered as a referrer.",
    });
  }
  const compact = customerId.replace(/-/g, "");
  const referrer: ReferrerOut = {
    id: `refr-${String(mockState.referrers.length + 1).padStart(4, "0")}`,
    customer_id: customerId,
    referral_code: `REF-${customerId.slice(0, 8).toUpperCase()}`,
    referral_link_token: `rlt_${compact.slice(0, 12)}`,
    is_active: true,
    created_at: nowIso(),
  };
  mockState.referrers.unshift(referrer);
  mockState.referralsByReferrer[customerId] = [];
  return { ...referrer };
}

export async function getReferrer(customerId: string): Promise<ReferrerOut> {
  await mockDelay();
  const referrer = mockState.referrers.find((r) => r.customer_id === customerId);
  if (!referrer) {
    throw notFound("Referrer not found", "This customer isn't registered as a referrer.");
  }
  return { ...referrer };
}

export async function getReferrerEarnings(customerId: string): Promise<EarningsOut> {
  await mockDelay();
  const referrals = mockState.referralsByReferrer[customerId] ?? [];
  return {
    referrer_customer_id: customerId,
    total_earned_micros: referrals.reduce((sum, r) => sum + r.total_earned_micros, 0),
    total_referred_spend_micros: referrals.reduce(
      (sum, r) => sum + r.total_referred_spend_micros,
      0,
    ),
    total_referrals: referrals.length,
    active_referrals: referrals.filter((r) => r.status === "active").length,
  };
}

export async function listReferrerReferrals(
  customerId: string,
  _cursor?: string,
): Promise<CursorPage<ReferralOut>> {
  await mockDelay();
  const referrals = mockState.referralsByReferrer[customerId] ?? [];
  return { data: referrals.map((r) => ({ ...r })), has_more: false, next_cursor: null };
}

// --- Individual referrals ----------------------------------------------------

export async function attributeReferral(body: AttributeRequest): Promise<AttributeResponse> {
  await mockDelay();
  const referrer = mockState.referrers.find((r) =>
    body.code ? r.referral_code === body.code : body.link_token ? r.referral_link_token === body.link_token : false,
  );
  if (!referrer) {
    throw notFound("No matching referrer", "No referrer matches that code or link token.");
  }
  if (referrer.customer_id === body.customer_id) {
    throw new ApiProblem({
      status: 422,
      code: "validation_error",
      title: "Self-referral",
      detail: "A customer can't refer themselves.",
    });
  }
  if (allReferrals().some((r) => r.referred_customer_id === body.customer_id)) {
    throw new ApiProblem({
      status: 409,
      code: "conflict",
      title: "Already attributed",
      detail: "That customer is already attributed to a referrer.",
    });
  }
  const program = mockState.program;
  const referral: ReferralOut = {
    id: `rfl-${String(allReferrals().length + 1).padStart(4, "0")}`,
    referred_customer_id: body.customer_id,
    referred_external_id: `acct-${body.customer_id.slice(0, 8)}`,
    referral_code_used: referrer.referral_code,
    status: "active",
    reward_type: program?.reward_type ?? "revenue_share",
    total_earned_micros: 0,
    total_referred_spend_micros: 0,
    attributed_at: nowIso(),
    reward_window_ends_at:
      program?.reward_window_days != null
        ? new Date(Date.now() + program.reward_window_days * 86_400_000).toISOString()
        : null,
  };
  const list = mockState.referralsByReferrer[referrer.customer_id] ?? [];
  list.unshift(referral);
  mockState.referralsByReferrer[referrer.customer_id] = list;
  return {
    referral_id: referral.id,
    referrer_id: referrer.id,
    referred_customer_id: body.customer_id,
    status: referral.status,
  };
}

export async function revokeReferral(referralId: string): Promise<StatusResponse> {
  await mockDelay();
  for (const referrals of Object.values(mockState.referralsByReferrer)) {
    const match = referrals.find((r) => r.id === referralId);
    if (match) {
      match.status = "revoked";
      return { status: "revoked" };
    }
  }
  throw notFound("Referral not found");
}

export async function getReferralLedger(
  referralId: string,
  _cursor?: string,
): Promise<CursorPage<LedgerEntryOut>> {
  await mockDelay();
  const entries = mockState.ledgerByReferral[referralId] ?? [];
  return { data: entries.map((e) => ({ ...e })), has_more: false, next_cursor: null };
}

// --- Customer picker ---------------------------------------------------------

export async function listMarginCustomers(): Promise<MarginCustomerRow[]> {
  await mockDelay();
  return mockState.marginCustomers.map((row) => ({ ...row }));
}
