// Mock implementation — identical exported signatures to api.ts. Mutations are
// simulated coherently within a session via module-level state; errors are
// thrown as ApiProblem so the pages exercise the same failure paths.

import type { CursorPage } from "@/api/pagination";
import { ApiProblem } from "@/api/problem";
import { mockDelay } from "@/lib/api-provider";
import type { DateRange } from "@/lib/date-range";
import { resolveRange } from "@/lib/date-range";

import {
  buildMockTimeseries,
  emptyPastLimitReport,
  MOCK_BALANCES,
  MOCK_BILLING_PROFILES,
  MOCK_BUDGET_STATUS,
  MOCK_BUDGETS,
  MOCK_BUSINESS_MARGIN,
  MOCK_DIRECTORY,
  MOCK_GRANTS,
  MOCK_MARGIN_DETAILS,
  MOCK_MARGIN_ROWS,
  MOCK_PAST_LIMIT_REPORTS,
  MOCK_REVENUE_MODES,
  MOCK_REVENUE_PROFILES,
  MOCK_SUB_INVOICES,
  MOCK_SUBSCRIPTIONS,
  MOCK_TRANSACTIONS,
  MOCK_TREND_POINTS,
  MOCK_USAGE_ANALYTICS,
  MOCK_USAGE_INVOICES,
  type MockCustomer,
} from "./mock-data";
import type {
  BalanceResponse,
  BudgetConfigIn,
  BudgetConfigOut,
  BudgetStatusOut,
  BusinessMarginOut,
  ConfigureAutoTopUpRequest,
  CreateCustomerRequest,
  CreateGrantRequest,
  CreateTopUpRequest,
  CreditRequest,
  CustomerBillingProfileIn,
  CustomerBillingProfileOut,
  CustomerMarginOut,
  CustomerResponse,
  DebitCreditResponse,
  DebitRequest,
  GrantOut,
  MarginListOut,
  MarginTrendOut,
  PastLimitReport,
  PreCheckResponse,
  RevenueModeOut,
  RevenueProfileIn,
  RevenueProfileOut,
  StatusResponse,
  StripeSubscriptionOut,
  SubscribeIn,
  SubscriptionInvoiceOut,
  TopUpCheckoutResponse,
  UsageAnalyticsResponse,
  UsageInvoiceOut,
  UsageTimeseriesResponse,
  WalletTransactionOut,
  WithdrawRequest,
  WithdrawResponse,
} from "./types";

// ---------------------------------------------------------------------------
// Session state (reset on reload)

const directory: MockCustomer[] = [...MOCK_DIRECTORY];
const marginRows = [...MOCK_MARGIN_ROWS];
const marginDetails: Record<string, CustomerMarginOut> = { ...MOCK_MARGIN_DETAILS };
const balances: Record<string, BalanceResponse> = structuredClone(MOCK_BALANCES);
const transactions: Record<string, WalletTransactionOut[]> =
  structuredClone(MOCK_TRANSACTIONS);
const grants: Record<string, GrantOut[]> = structuredClone(MOCK_GRANTS);
const budgets: Record<string, BudgetConfigOut> = structuredClone(MOCK_BUDGETS);
const billingProfiles: Record<string, CustomerBillingProfileOut> =
  structuredClone(MOCK_BILLING_PROFILES);
const revenueProfiles: Record<string, RevenueProfileOut> =
  structuredClone(MOCK_REVENUE_PROFILES);
const revenueModes: Record<string, RevenueModeOut> =
  structuredClone(MOCK_REVENUE_MODES);
const subscriptions: Record<string, StripeSubscriptionOut> =
  structuredClone(MOCK_SUBSCRIPTIONS);

function notFound(detail: string): ApiProblem {
  return new ApiProblem({
    status: 404,
    code: "not_found",
    title: "Not found",
    detail,
  });
}

function requireCustomer(customerId: string): MockCustomer {
  const found = directory.find((entry) => entry.id === customerId);
  if (!found) throw notFound("Unknown customer.");
  return found;
}

/**
 * A pooled seat's balance IS the billing owner's (a seat never carries its
 * own wallet) — mirror that here so seat ids resolve to their parent
 * business rather than a fabricated standalone balance.
 */
function resolveBillingOwner(customerId: string): {
  billing_owner_id: string;
  billing_owner_external_id: string;
  is_pooled_seat: boolean;
} {
  const customer = directory.find((entry) => entry.id === customerId);
  if (customer?.parent_external_id) {
    const owner = directory.find(
      (entry) => entry.external_id === customer.parent_external_id,
    );
    if (owner) {
      return {
        billing_owner_id: owner.id,
        billing_owner_external_id: owner.external_id,
        is_pooled_seat: true,
      };
    }
  }
  return {
    billing_owner_id: customerId,
    billing_owner_external_id: customer?.external_id ?? "",
    is_pooled_seat: false,
  };
}

function balanceOf(customerId: string): BalanceResponse {
  const existing = balances[customerId];
  if (existing) return existing;
  const owner = resolveBillingOwner(customerId);
  // A pooled seat has no wallet of its own — the real GET reads the OWNER's
  // wallet, so a fresh seat balance seeds from the owner's actual figures
  // (never a fabricated zero) when the owner already has one on record.
  const ownerBalance = owner.is_pooled_seat ? balances[owner.billing_owner_id] : undefined;
  const fresh: BalanceResponse = ownerBalance
    ? { ...ownerBalance, ...owner }
    : {
        balance_micros: 0,
        currency: "usd",
        ...owner,
        promo_micros: 0,
        expiring_micros: 0,
        next_expiry_at: null,
        negative_since: null,
      };
  balances[customerId] = fresh;
  return fresh;
}

function pushTransaction(
  customerId: string,
  type: string,
  amountMicros: number,
  description: string,
  referenceId: string,
): WalletTransactionOut {
  const balance = balanceOf(customerId);
  balance.balance_micros += amountMicros;
  balance.negative_since =
    balance.balance_micros < 0
      ? (balance.negative_since ?? new Date().toISOString())
      : null;
  const row: WalletTransactionOut = {
    id: crypto.randomUUID(),
    transaction_type: type,
    amount_micros: amountMicros,
    balance_after_micros: balance.balance_micros,
    description,
    reference_id: referenceId,
    created_at: new Date().toISOString(),
  };
  transactions[customerId] = [row, ...(transactions[customerId] ?? [])];
  return row;
}

function page<T>(rows: T[]): CursorPage<T> {
  return { data: rows, has_more: false, next_cursor: null };
}

// ---------------------------------------------------------------------------
// Margin

export async function listCustomerMargins(range: DateRange): Promise<MarginListOut> {
  await mockDelay();
  const resolved = resolveRange(range);
  return {
    customers: marginRows,
    period: { start: resolved.start_date, end: resolved.end_date },
  };
}

export async function getCustomerMargin(
  customerId: string,
  range: DateRange,
): Promise<CustomerMarginOut> {
  await mockDelay();
  const detail = marginDetails[customerId];
  if (!detail) throw notFound("Unknown customer.");
  const resolved = resolveRange(range);
  return {
    ...detail,
    period: { start: resolved.start_date, end: resolved.end_date },
  };
}

export async function getMarginTrend(
  customerId: string,
  periods: number,
): Promise<MarginTrendOut> {
  await mockDelay();
  requireCustomer(customerId);
  return {
    customer_id: customerId,
    points: MOCK_TREND_POINTS.slice(-Math.min(Math.max(periods, 1), 36)),
  };
}

export async function getRevenueProfile(customerId: string): Promise<RevenueProfileOut> {
  await mockDelay();
  requireCustomer(customerId);
  const profile = revenueProfiles[customerId];
  if (!profile) throw notFound("No recurring revenue profile for this customer.");
  return profile;
}

export async function putRevenueProfile(
  customerId: string,
  body: RevenueProfileIn,
): Promise<RevenueProfileOut> {
  await mockDelay();
  requireCustomer(customerId);
  const saved: RevenueProfileOut = {
    recurring_amount_micros: body.recurring_amount_micros,
    currency: body.currency,
    interval: body.interval,
    effective_from: body.effective_from ?? new Date().toISOString(),
    effective_to: body.effective_to ?? null,
  };
  revenueProfiles[customerId] = saved;
  return saved;
}

export async function getRevenueMode(customerId: string): Promise<RevenueModeOut> {
  await mockDelay();
  requireCustomer(customerId);
  return revenueModes[customerId] ?? { revenue_mode: "", resolved: "billed" };
}

export async function putRevenueMode(
  customerId: string,
  revenueMode: string,
): Promise<RevenueModeOut> {
  await mockDelay();
  requireCustomer(customerId);
  if (revenueMode !== "" && revenueMode !== "billed" && revenueMode !== "metered_only") {
    throw new ApiProblem({
      status: 422,
      code: "invalid_revenue_mode",
      title: "Invalid revenue mode",
      detail: `revenue_mode must be one of '', 'billed', 'metered_only'; got '${revenueMode}'`,
    });
  }
  const resolved = revenueMode === "" ? "billed" : revenueMode;
  const saved: RevenueModeOut = { revenue_mode: revenueMode, resolved };
  revenueModes[customerId] = saved;
  return saved;
}

export async function getBusinessMargin(
  externalId: string,
  _range: DateRange,
): Promise<BusinessMarginOut> {
  await mockDelay();
  if (externalId !== MOCK_BUSINESS_MARGIN.external_id) {
    throw notFound("Not a business customer.");
  }
  return MOCK_BUSINESS_MARGIN;
}

// ---------------------------------------------------------------------------
// Platform — create customer

export async function createCustomer(
  body: CreateCustomerRequest,
): Promise<CustomerResponse> {
  await mockDelay();
  if (directory.some((entry) => entry.external_id === body.external_id)) {
    throw new ApiProblem({
      status: 409,
      code: "conflict",
      title: "Conflict",
      detail: `A customer with external_id '${body.external_id}' already exists.`,
    });
  }
  const id = crypto.randomUUID();
  directory.push({
    id,
    external_id: body.external_id,
    account_type: body.account_type,
    parent_external_id: body.parent_external_id,
    stripe_customer_id: body.stripe_customer_id,
  });
  const zeroRow = {
    customer_id: id,
    subscription_revenue_micros: 0,
    usage_billed_micros: 0,
    usage_revenue_micros: 0,
    provider_cost_micros: 0,
    unresolved_event_count: 0,
    unpriced_event_count: 0,
    gross_margin_micros: 0,
    margin_percentage: 0,
  };
  marginRows.push(zeroRow);
  marginDetails[id] = {
    ...zeroRow,
    external_id: body.external_id,
    period: { start: "2026-07-01", end: "2026-07-24" },
    revenue_mode: "billed",
    event_count: 0,
    total_revenue_micros: 0,
  };
  return {
    id,
    external_id: body.external_id,
    stripe_customer_id: body.stripe_customer_id,
    status: "active",
  };
}

// ---------------------------------------------------------------------------
// Metering — usage analytics + past-limit report

export async function getUsageAnalytics(
  customerId: string,
  _range: DateRange,
): Promise<UsageAnalyticsResponse> {
  await mockDelay();
  requireCustomer(customerId);
  return (
    MOCK_USAGE_ANALYTICS[customerId] ?? {
      total_events: 0,
      total_billed_cost_micros: 0,
      total_provider_cost_micros: 0,
      unresolved_event_count: 0,
      unpriced_event_count: 0,
      usage_markup_margin_micros: 0,
      by_provider: [],
      by_event_type: [],
      by_customer: [],
      by_task_type: [],
      by_tag: [],
      breakdowns: {},
    }
  );
}

export async function getUsageTimeseries(
  customerId: string,
  _range: DateRange,
): Promise<UsageTimeseriesResponse> {
  await mockDelay();
  requireCustomer(customerId);
  return buildMockTimeseries(customerId);
}

export async function getPastLimitReport(customerId: string): Promise<PastLimitReport> {
  await mockDelay();
  requireCustomer(customerId);
  return MOCK_PAST_LIMIT_REPORTS[customerId] ?? emptyPastLimitReport(customerId);
}

// ---------------------------------------------------------------------------
// Billing — wallet + money movement

export async function getBalance(customerId: string): Promise<BalanceResponse> {
  await mockDelay();
  requireCustomer(customerId);
  return balanceOf(customerId);
}

export async function createTopUp(
  customerId: string,
  body: CreateTopUpRequest,
): Promise<TopUpCheckoutResponse> {
  await mockDelay();
  requireCustomer(customerId);
  // The mock "completes" the checkout instantly so the balance moves.
  pushTransaction(
    customerId,
    "TOP_UP",
    body.amount_micros,
    "Stripe Checkout top-up (mock)",
    body.idempotency_key,
  );
  return { checkout_url: "https://checkout.stripe.com/c/pay/mock-session" };
}

export async function withdraw(
  customerId: string,
  body: WithdrawRequest,
): Promise<WithdrawResponse> {
  await mockDelay();
  requireCustomer(customerId);
  const balance = balanceOf(customerId);
  const available = balance.balance_micros - (balance.promo_micros ?? 0);
  if (body.amount_micros > available) {
    throw new ApiProblem({
      status: 422,
      code: "would_overdraw",
      title: "Would overdraw",
      detail: "Amount exceeds the withdrawable (non-promo) balance.",
    });
  }
  const row = pushTransaction(
    customerId,
    "WITHDRAWAL",
    -body.amount_micros,
    body.description || "Withdrawal",
    body.idempotency_key,
  );
  return { transaction_id: row.id, balance_micros: balance.balance_micros };
}

function findByExternalId(externalId: string): MockCustomer {
  const found = directory.find((entry) => entry.external_id === externalId);
  if (!found) throw notFound(`Unknown customer '${externalId}'.`);
  return found;
}

export async function creditWallet(body: CreditRequest): Promise<DebitCreditResponse> {
  await mockDelay();
  const customer = findByExternalId(body.customer_id);
  const row = pushTransaction(
    customer.id,
    "ADJUSTMENT",
    body.amount_micros,
    `Manual credit — ${body.reference}`,
    body.reference,
  );
  return {
    transaction_id: row.id,
    new_balance_micros: balanceOf(customer.id).balance_micros,
  };
}

export async function debitWallet(body: DebitRequest): Promise<DebitCreditResponse> {
  await mockDelay();
  const customer = findByExternalId(body.customer_id);
  const balance = balanceOf(customer.id);
  if (!body.allow_negative && balance.balance_micros - body.amount_micros < 0) {
    throw new ApiProblem({
      status: 422,
      code: "would_overdraw",
      title: "Would overdraw",
      detail: "Debit would take the balance negative (allow_negative not set).",
    });
  }
  const row = pushTransaction(
    customer.id,
    "DEBIT",
    -body.amount_micros,
    `Manual debit — ${body.reference}`,
    body.reference,
  );
  return { transaction_id: row.id, new_balance_micros: balance.balance_micros };
}

export async function preCheck(customerId: string): Promise<PreCheckResponse> {
  await mockDelay();
  requireCustomer(customerId);
  const balance = balanceOf(customerId);
  if (balance.balance_micros <= 0) {
    return {
      allowed: false,
      reason: "insufficient_funds",
      balance_micros: balance.balance_micros,
    };
  }
  return { allowed: true, reason: null, balance_micros: balance.balance_micros };
}

export async function listTransactions(
  customerId: string,
  _cursor?: string,
): Promise<CursorPage<WalletTransactionOut>> {
  await mockDelay();
  requireCustomer(customerId);
  return page(transactions[customerId] ?? []);
}

export async function listGrants(
  customerId: string,
  options: { status?: string; cursor?: string },
): Promise<CursorPage<GrantOut>> {
  await mockDelay();
  requireCustomer(customerId);
  const rows = grants[customerId] ?? [];
  return page(
    options.status ? rows.filter((row) => row.status === options.status) : rows,
  );
}

export async function createGrant(
  customerId: string,
  body: CreateGrantRequest,
): Promise<GrantOut> {
  await mockDelay();
  requireCustomer(customerId);
  const expiresAt =
    body.expires_at ??
    (body.expires_in_days
      ? new Date(Date.now() + body.expires_in_days * 86_400_000).toISOString()
      : null);
  pushTransaction(
    customerId,
    "GRANT",
    body.amount_micros,
    body.description || "Credit grant",
    body.idempotency_key,
  );
  const grant: GrantOut = {
    id: crypto.randomUUID(),
    kind: body.kind,
    granted_micros: body.amount_micros,
    remaining_micros: body.amount_micros,
    expired_micros: 0,
    voided_micros: 0,
    currency: "usd",
    status: "active",
    source: "api",
    expires_at: expiresAt,
    warning_sent_at: null,
    created_at: new Date().toISOString(),
    balance_micros: balanceOf(customerId).balance_micros,
    transaction_id: crypto.randomUUID(),
  };
  grants[customerId] = [grant, ...(grants[customerId] ?? [])];
  return grant;
}

export async function voidGrant(customerId: string, grantId: string): Promise<GrantOut> {
  await mockDelay();
  requireCustomer(customerId);
  const grant = (grants[customerId] ?? []).find((row) => row.id === grantId);
  if (!grant) throw notFound("Unknown grant.");
  if (grant.status === "voided") return grant;
  const clawback = Math.min(grant.remaining_micros, balanceOf(customerId).balance_micros);
  pushTransaction(customerId, "GRANT_VOID", -clawback, "Grant voided", grant.id);
  grant.voided_micros = grant.remaining_micros;
  grant.remaining_micros = 0;
  grant.status = "voided";
  grant.balance_micros = balanceOf(customerId).balance_micros;
  grant.transaction_id = crypto.randomUUID();
  return grant;
}

// ---------------------------------------------------------------------------
// Billing — budget, profile, auto top-up

export async function getCustomerBudget(customerId: string): Promise<BudgetConfigOut> {
  await mockDelay();
  requireCustomer(customerId);
  return (
    budgets[customerId] ?? {
      cap_micros: 0,
      enforce_mode: "alert_only",
      hard_stop_pct: 100,
      alert_levels: [],
      fail_closed: false,
    }
  );
}

export async function putCustomerBudget(
  customerId: string,
  body: BudgetConfigIn,
): Promise<BudgetConfigOut> {
  await mockDelay();
  requireCustomer(customerId);
  const saved: BudgetConfigOut = {
    cap_micros: body.cap_micros,
    enforce_mode: body.enforce_mode,
    hard_stop_pct: body.hard_stop_pct,
    alert_levels: body.alert_levels ?? [],
    fail_closed: body.fail_closed,
  };
  budgets[customerId] = saved;
  return saved;
}

export async function getBudgetStatus(customerId: string): Promise<BudgetStatusOut> {
  await mockDelay();
  requireCustomer(customerId);
  const config = budgets[customerId];
  return (
    MOCK_BUDGET_STATUS[customerId] ?? {
      period: "2026-07",
      spend_micros: 0,
      cap_micros: config?.cap_micros ?? 0,
      pct: 0,
      enforce_mode: config?.enforce_mode ?? "alert_only",
    }
  );
}

export async function getBillingProfile(
  customerId: string,
): Promise<CustomerBillingProfileOut> {
  await mockDelay();
  requireCustomer(customerId);
  // Mirrors the real GET (billing_endpoints get_customer_billing_profile):
  // it always answers the OWNER's effective profile — a pooled seat reads
  // real floor values from its business, never fabricated nulls.
  const owner = resolveBillingOwner(customerId);
  const ownerProfile = billingProfiles[owner.billing_owner_id];
  return {
    ...owner,
    min_balance_micros: ownerProfile?.min_balance_micros ?? null,
    soft_min_balance_micros: ownerProfile?.soft_min_balance_micros ?? null,
    topup_grant_expiry_days: ownerProfile?.topup_grant_expiry_days ?? null,
  };
}

export async function putBillingProfile(
  customerId: string,
  body: CustomerBillingProfileIn,
): Promise<CustomerBillingProfileOut> {
  await mockDelay();
  requireCustomer(customerId);
  // Mirrors the server's pooled-seat refusal (billing_endpoints
  // put_customer_billing_profile): writing floors to a seat's own profile row
  // would be silently ignored (the gate reads the OWNER's row), and writing
  // them to the owner's row instead would silently change every sibling
  // seat's policy — so the real PUT 422s rather than doing either quietly.
  const owner = resolveBillingOwner(customerId);
  if (owner.is_pooled_seat) {
    throw new ApiProblem({
      status: 422,
      code: "invalid_config",
      title: "Invalid billing profile",
      detail: `This customer is a pooled seat billed through '${owner.billing_owner_external_id}' — set overdraft/expiry floors on the billing owner, not the seat.`,
      extensions: { billing_owner_external_id: owner.billing_owner_external_id },
    });
  }
  // Mirror the server's floor validation (billing_endpoints put_billing_profile):
  // the hard value is an allowed-overdraft MAGNITUDE ≥ 0, and the soft wire
  // value must not exceed the effective hard value (tenant default = 0).
  const min = body.min_balance_micros ?? null;
  if (min !== null && min < 0) {
    throw new ApiProblem({
      status: 422,
      code: "invalid_config",
      title: "Invalid billing profile",
      detail:
        "min_balance_micros must be >= 0 (allowed overdraft magnitude), or null to inherit the tenant default",
    });
  }
  const soft = body.soft_min_balance_micros ?? null;
  const effectiveHard = min ?? billingProfiles[customerId]?.min_balance_micros ?? 0;
  if (soft !== null && soft > effectiveHard) {
    throw new ApiProblem({
      status: 422,
      code: "invalid_config",
      title: "Invalid billing profile",
      detail:
        "soft_min_balance_micros must not exceed the hard floor value (the allowed overdraft)",
    });
  }
  const saved: CustomerBillingProfileOut = {
    ...resolveBillingOwner(customerId),
    min_balance_micros: body.min_balance_micros ?? null,
    soft_min_balance_micros: body.soft_min_balance_micros ?? null,
    topup_grant_expiry_days: body.topup_grant_expiry_days ?? null,
  };
  billingProfiles[customerId] = saved;
  return saved;
}

export async function listCustomerUsageInvoices(
  customerId: string,
  _cursor?: string,
): Promise<CursorPage<UsageInvoiceOut>> {
  await mockDelay();
  requireCustomer(customerId);
  return page(MOCK_USAGE_INVOICES[customerId] ?? []);
}

export async function configureAutoTopUp(
  customerId: string,
  _body: ConfigureAutoTopUpRequest,
): Promise<StatusResponse> {
  await mockDelay();
  requireCustomer(customerId);
  return { status: "ok" };
}

// ---------------------------------------------------------------------------
// Metering — pricing
//
// ⚠ NOTHING TO MOCK (#369). The resolved markup read, the override write and
// the override delete all called routes that are deleted with the record
// behind them.


// ---------------------------------------------------------------------------
// Subscriptions

export async function getSubscription(
  customerId: string,
): Promise<StripeSubscriptionOut> {
  await mockDelay();
  requireCustomer(customerId);
  const sub = subscriptions[customerId];
  if (!sub) throw notFound("No subscription for this customer.");
  return sub;
}

export async function listSubscriptionInvoices(
  customerId: string,
  _cursor?: string,
): Promise<CursorPage<SubscriptionInvoiceOut>> {
  await mockDelay();
  requireCustomer(customerId);
  return page(MOCK_SUB_INVOICES[customerId] ?? []);
}

export async function subscribeCustomer(
  externalId: string,
  body: SubscribeIn,
): Promise<Record<string, unknown>> {
  await mockDelay();
  const customer = findByExternalId(externalId);
  subscriptions[customer.id] = {
    id: crypto.randomUUID(),
    stripe_subscription_id: `sub_mock_${externalId}`,
    stripe_product_name: `UBB Platform — ${body.plan_key}`,
    status: "active",
    amount_micros: 149_000_000,
    currency: "usd",
    interval: "month",
    current_period_start: "2026-07-24T00:00:00Z",
    current_period_end: "2026-08-24T00:00:00Z",
    last_synced_at: new Date().toISOString(),
  };
  return { status: "subscribed", plan_key: body.plan_key, seats: body.seats };
}

function requireSubscription(externalId: string): StripeSubscriptionOut {
  const customer = findByExternalId(externalId);
  const sub = subscriptions[customer.id];
  if (!sub) throw notFound("No subscription to change.");
  return sub;
}

export async function cancelSubscription(
  externalId: string,
  atPeriodEnd: boolean,
): Promise<Record<string, unknown>> {
  await mockDelay();
  const sub = requireSubscription(externalId);
  sub.status = atPeriodEnd ? "active" : "canceled";
  sub.last_synced_at = new Date().toISOString();
  return { status: "ok", at_period_end: atPeriodEnd };
}

export async function pauseSubscription(
  externalId: string,
): Promise<Record<string, unknown>> {
  await mockDelay();
  const sub = requireSubscription(externalId);
  sub.status = "paused";
  sub.last_synced_at = new Date().toISOString();
  return { status: "ok" };
}

export async function resumeSubscription(
  externalId: string,
): Promise<Record<string, unknown>> {
  await mockDelay();
  const sub = requireSubscription(externalId);
  sub.status = "active";
  sub.last_synced_at = new Date().toISOString();
  return { status: "ok" };
}

export async function setSeats(
  externalId: string,
  seats: number,
): Promise<Record<string, unknown>> {
  await mockDelay();
  findByExternalId(externalId);
  return { status: "ok", seats };
}
