import { http, HttpResponse } from "msw";
import * as fx from "./fixtures";

const ok = { status: "ok" };
const rid = (p: string) => `${p}_${Math.random().toString(36).slice(2, 10)}`;

/**
 * MSW handlers for the mock provider. Reads return representative fixtures;
 * writes return plausible success payloads (echoing the request where the UI
 * uses the result). Base paths are relative (VITE_API_URL is empty in mock
 * mode, so the client hits same-origin /api/v1/*).
 */
export const handlers = [
  // ---------------- tenant ----------------
  http.get("/api/v1/tenant/config", () => HttpResponse.json(fx.tenantConfig)),
  http.patch("/api/v1/tenant/config", async ({ request }) => {
    const body = (await request.json()) as Record<string, unknown>;
    return HttpResponse.json({ ...fx.tenantConfig, ...body });
  }),
  http.get("/api/v1/tenant/api-keys", () => HttpResponse.json(fx.page(fx.apiKeys))),
  http.post("/api/v1/tenant/api-keys", async ({ request }) => {
    const body = (await request.json()) as { label?: string; is_test?: boolean };
    const prefix = body.is_test ? "sk_test" : "sk_live";
    return HttpResponse.json({ id: rid("key"), key: `${prefix}_${rid("")}`, key_prefix: `${prefix}_${rid("").slice(0, 3)}`, label: body.label ?? "", is_active: true, created_at: new Date().toISOString() });
  }),
  http.delete("/api/v1/tenant/api-keys/:id", () => HttpResponse.json(ok)),
  http.post("/api/v1/tenant/api-keys/:id/rotate", () => HttpResponse.json({ key: `sk_live_${rid("")}` })),
  http.get("/api/v1/tenant/billing-periods", () => HttpResponse.json(fx.page(fx.billingPeriods))),
  http.get("/api/v1/tenant/invitations", () => HttpResponse.json(fx.page(fx.invitations))),
  http.post("/api/v1/tenant/invitations", async ({ request }) => {
    const body = (await request.json()) as { email: string; role: string };
    return HttpResponse.json({ id: rid("inv"), email: body.email, role: body.role, status: "pending", created_at: new Date().toISOString() });
  }),
  http.delete("/api/v1/tenant/invitations/:id", () => HttpResponse.json(ok)),
  http.get("/api/v1/tenant/invoices", () => HttpResponse.json(fx.page(fx.tenantInvoices))),
  http.get("/api/v1/tenant/members", () => HttpResponse.json(fx.page(fx.members))),
  http.patch("/api/v1/tenant/members/:id", async ({ request, params }) => {
    const body = (await request.json()) as { role: string };
    return HttpResponse.json({ ...fx.members[0], id: params.id as string, role: body.role });
  }),
  http.delete("/api/v1/tenant/members/:id", () => HttpResponse.json(ok)),
  http.get("/api/v1/tenant/sandbox", () => HttpResponse.json({ enabled: false })),
  http.post("/api/v1/tenant/sandbox", () => HttpResponse.json({ enabled: true })),

  // ---------------- billing ----------------
  http.get("/api/v1/billing/analytics/revenue", () => HttpResponse.json(fx.revenueAnalytics)),
  http.get("/api/v1/billing/budget", () => HttpResponse.json(fx.budgetConfig)),
  http.put("/api/v1/billing/budget", async ({ request }) => HttpResponse.json({ ...fx.budgetConfig, ...(await request.json() as object) })),
  http.get("/api/v1/billing/postpaid-config", () => HttpResponse.json(fx.postpaidConfig)),
  http.put("/api/v1/billing/postpaid-config", async ({ request }) => HttpResponse.json({ ...fx.postpaidConfig, ...(await request.json() as object) })),
  http.post("/api/v1/billing/credit", () => HttpResponse.json({ new_balance_micros: fx.balance.balance_micros + fx.d(100), transaction_id: rid("wtx") })),
  http.post("/api/v1/billing/debit", () => HttpResponse.json({ new_balance_micros: fx.balance.balance_micros - fx.d(50), transaction_id: rid("wtx") })),
  http.post("/api/v1/billing/pre-check", () => HttpResponse.json({ allowed: true, reason: null, balance_micros: fx.balance.balance_micros, task_id: null, parent_task_id: null, provider_cost_limit_micros: fx.d(2), floor_snapshot_micros: fx.d(1) })),
  http.get("/api/v1/billing/tenant/usage-invoices", () => HttpResponse.json(fx.page(fx.tenantUsageInvoices))),
  // billing — per customer
  http.get("/api/v1/billing/customers/:id/balance", () => HttpResponse.json(fx.balance)),
  http.get("/api/v1/billing/customers/:id/transactions", () => HttpResponse.json(fx.page(fx.walletTransactions))),
  http.post("/api/v1/billing/customers/:id/top-up", () => HttpResponse.json({ checkout_url: "" })),
  http.post("/api/v1/billing/customers/:id/withdraw", () => HttpResponse.json({ transaction_id: rid("wtx"), balance_micros: fx.balance.balance_micros - fx.d(20) })),
  http.post("/api/v1/billing/customers/:id/refund", () => HttpResponse.json({ refund_id: rid("ref"), balance_micros: fx.balance.balance_micros + fx.d(5) })),
  http.put("/api/v1/billing/customers/:id/auto-top-up", () => HttpResponse.json(ok)),
  http.get("/api/v1/billing/customers/:id/grants", () => HttpResponse.json(fx.page(fx.grants))),
  http.post("/api/v1/billing/customers/:id/grants", async ({ request }) => {
    const b = (await request.json()) as { kind: string; amount_micros: number; description?: string };
    return HttpResponse.json({ ...fx.grants[0], id: rid("grant"), kind: b.kind, granted_micros: b.amount_micros, remaining_micros: b.amount_micros, status: "active", created_at: new Date().toISOString() });
  }),
  http.post("/api/v1/billing/customers/:id/grants/:gid/void", ({ params }) => HttpResponse.json({ ...fx.grants[0], id: params.gid as string, remaining_micros: 0, status: "voided" })),
  http.get("/api/v1/billing/customers/:id/budget", () => HttpResponse.json(fx.budgetConfig)),
  http.put("/api/v1/billing/customers/:id/budget", async ({ request }) => HttpResponse.json({ ...fx.budgetConfig, ...(await request.json() as object) })),
  http.get("/api/v1/billing/customers/:id/budget/status", () => HttpResponse.json(fx.budgetStatus)),
  http.get("/api/v1/billing/customers/:id/billing-profile", () => HttpResponse.json(fx.billingProfile)),
  http.put("/api/v1/billing/customers/:id/billing-profile", async ({ request }) => HttpResponse.json({ ...fx.billingProfile, ...(await request.json() as object) })),
  http.get("/api/v1/billing/customers/:id/usage-invoices", () => HttpResponse.json(fx.page(fx.usageInvoices))),

  // ---------------- metering ----------------
  http.get("/api/v1/metering/analytics/usage", () => HttpResponse.json(fx.usageAnalytics)),
  http.get("/api/v1/metering/analytics/usage/timeseries", () => HttpResponse.json(fx.usageTimeseries)),
  http.get("/api/v1/metering/customers/:id/usage", () => HttpResponse.json(fx.page(fx.usageEvents))),
  http.get("/api/v1/metering/usage/:eventId", () => HttpResponse.json(fx.usageEventDetail)),
  http.post("/api/v1/metering/usage", () => HttpResponse.json({ event_id: rid("evt"), new_balance_micros: fx.balance.balance_micros, suspended: false, provider_cost_micros: fx.d(0.42), billed_cost_micros: fx.d(0.68), units: 1240, stop: false, uncosted_metrics: [], service_id: "", agent_id: "" })),
  http.post("/api/v1/metering/tasks/:taskId/close", ({ params }) => HttpResponse.json({ task_id: params.taskId as string, parent_task_id: null, status: "closed", total_billed_cost_micros: fx.d(4.2), total_provider_cost_micros: fx.d(2.6), event_count: 12 })),
  http.get("/api/v1/metering/pricing/markup", () => HttpResponse.json(fx.tenantMarkup)),
  http.put("/api/v1/metering/pricing/markup", async ({ request }) => HttpResponse.json({ ...fx.tenantMarkup, ...(await request.json() as object) })),
  http.get("/api/v1/metering/pricing/rate-cards", () => HttpResponse.json(fx.page(fx.books))),
  http.post("/api/v1/metering/pricing/rate-cards", async ({ request }) => {
    const b = (await request.json()) as Record<string, unknown>;
    return HttpResponse.json({ ...fx.books[0], id: rid("book"), version: 1, is_default: false, ...b });
  }),
  http.post("/api/v1/metering/pricing/rate-cards/:id/publish", ({ params }) => HttpResponse.json({ ...fx.books[0], id: params.id as string, version: (fx.books[0]?.version ?? 0) + 1 })),
  http.get("/api/v1/metering/pricing/rate-cards/:id/rates", () => HttpResponse.json(fx.page(fx.rates))),
  http.post("/api/v1/metering/pricing/rate-cards/:id/rates", async ({ request }) => {
    const b = (await request.json()) as Record<string, unknown>;
    return HttpResponse.json({ ...fx.rates[0], id: rid("rate"), valid_from: new Date().toISOString(), ...b });
  }),
  http.delete("/api/v1/metering/pricing/rate-cards/:id/rates/:rateId", () => HttpResponse.json(ok)),
  http.get("/api/v1/metering/pricing/customers/:id/markup", () => HttpResponse.json(fx.tenantMarkup)),
  http.put("/api/v1/metering/pricing/customers/:id/markup", async ({ request }) => HttpResponse.json({ ...fx.tenantMarkup, ...(await request.json() as object) })),
  http.delete("/api/v1/metering/pricing/customers/:id/markup", () => HttpResponse.json(ok)),
  http.post("/api/v1/metering/pricing/customers/:id/rate-card", () => HttpResponse.json(ok)),

  // ---------------- margin ----------------
  http.get("/api/v1/margin/summary", () => HttpResponse.json(fx.marginSummary)),
  http.get("/api/v1/margin/customers", () => HttpResponse.json(fx.marginList)),
  http.get("/api/v1/margin/by-dimension", () => HttpResponse.json(fx.marginByDimension)),
  http.get("/api/v1/margin/unprofitable", () => HttpResponse.json(fx.unprofitable)),
  http.get("/api/v1/margin/threshold", () => HttpResponse.json(fx.marginThreshold)),
  http.put("/api/v1/margin/threshold", async ({ request }) => HttpResponse.json({ ...fx.marginThreshold, ...(await request.json() as object) })),
  http.get("/api/v1/margin/business/:externalId", () => HttpResponse.json(fx.businessMargin)),
  http.get("/api/v1/margin/customers/:id/revenue", () => HttpResponse.json(fx.revenueProfile)),
  http.put("/api/v1/margin/customers/:id/revenue", async ({ request }) => HttpResponse.json({ ...fx.revenueProfile, ...(await request.json() as object) })),
  http.get("/api/v1/margin/customers/:id/revenue-mode", () => HttpResponse.json(fx.revenueMode)),
  http.put("/api/v1/margin/customers/:id/revenue-mode", async ({ request }) => HttpResponse.json({ ...fx.revenueMode, ...(await request.json() as object) })),
  http.get("/api/v1/margin/customers/:id/trend", () => HttpResponse.json(fx.marginTrend)),
  http.get("/api/v1/margin/customers/:id", () => HttpResponse.json(fx.customerMargin)),

  // ---------------- platform ----------------
  http.get("/api/v1/platform/accounts/business/:externalId", () => HttpResponse.json({ external_id: fx.EXTERNAL_ID, account_type: "business" })),
  http.post("/api/v1/platform/customers", async ({ request }) => {
    const b = (await request.json()) as { external_id: string; stripe_customer_id?: string };
    return HttpResponse.json({ id: rid("cus"), external_id: b.external_id, stripe_customer_id: b.stripe_customer_id ?? "", status: "active" });
  }),
  http.post("/api/v1/platform/customers/:ext/seats", () => HttpResponse.json(ok)),
  http.post("/api/v1/platform/customers/:ext/subscribe", () => HttpResponse.json(ok)),
  http.post("/api/v1/platform/customers/:ext/subscription/cancel", () => HttpResponse.json(ok)),
  http.post("/api/v1/platform/customers/:ext/subscription/pause", () => HttpResponse.json(ok)),
  http.post("/api/v1/platform/customers/:ext/subscription/resume", () => HttpResponse.json(ok)),
  http.post("/api/v1/platform/plans", async ({ request }) => HttpResponse.json({ ...fx.plan, id: rid("plan"), ...(await request.json() as object) })),
  http.patch("/api/v1/platform/plans/:key", () => HttpResponse.json(ok)),

  // ---------------- subscriptions ----------------
  http.post("/api/v1/subscriptions/sync", () => HttpResponse.json({ synced: 3, skipped: 1, errors: 0 })),
  http.get("/api/v1/subscriptions/customers/:id/subscription", () => HttpResponse.json(fx.subscription)),
  http.get("/api/v1/subscriptions/customers/:id/invoices", () => HttpResponse.json(fx.page(fx.subscriptionInvoices))),

  // ---------------- referrals ----------------
  http.get("/api/v1/referrals/analytics/summary", () => HttpResponse.json(fx.analyticsSummary)),
  http.get("/api/v1/referrals/analytics/earnings", () => HttpResponse.json(fx.analyticsEarnings)),
  http.get("/api/v1/referrals/payouts/export", () => HttpResponse.json(fx.payoutExport)),
  http.post("/api/v1/referrals/attribute", () => HttpResponse.json({ referral_id: rid("rfl"), referrer_id: "ref_1", referred_customer_id: fx.CUSTOMER_ID, status: "attributed" })),
  http.get("/api/v1/referrals/program", () => HttpResponse.json(fx.program)),
  http.post("/api/v1/referrals/program", async ({ request }) => HttpResponse.json({ ...fx.program, id: rid("prog"), status: "active", ...(await request.json() as object) })),
  http.patch("/api/v1/referrals/program", async ({ request }) => HttpResponse.json({ ...fx.program, ...(await request.json() as object) })),
  http.delete("/api/v1/referrals/program", () => HttpResponse.json(ok)),
  http.post("/api/v1/referrals/program/reactivate", () => HttpResponse.json({ ...fx.program, status: "active" })),
  http.get("/api/v1/referrals/referrers", () => HttpResponse.json(fx.page(fx.referrers))),
  http.post("/api/v1/referrals/referrers", async ({ request }) => {
    const b = (await request.json()) as { customer_id: string };
    return HttpResponse.json({ ...fx.referrers[0], id: rid("ref"), customer_id: b.customer_id, referral_code: rid("CODE").toUpperCase(), referral_link_token: rid("tok"), created_at: new Date().toISOString() });
  }),
  http.get("/api/v1/referrals/referrers/:id/earnings", () => HttpResponse.json(fx.referrerEarnings)),
  http.get("/api/v1/referrals/referrers/:id/referrals", () => HttpResponse.json(fx.page(fx.referrals))),
  http.get("/api/v1/referrals/referrers/:id", ({ params }) => HttpResponse.json({ ...fx.referrers[0], customer_id: params.id as string })),
  http.delete("/api/v1/referrals/referrals/:id", () => HttpResponse.json(ok)),
  http.get("/api/v1/referrals/referrals/:id/ledger", () => HttpResponse.json(fx.page(fx.ledgerEntries))),

  // ---------------- webhooks ----------------
  http.get("/api/v1/webhooks/configs", () => HttpResponse.json(fx.page(fx.webhookConfigs))),
  http.post("/api/v1/webhooks/configs", async ({ request }) => {
    const b = (await request.json()) as { url: string; event_types: string[]; is_active?: boolean };
    return HttpResponse.json({ id: rid("wh"), url: b.url, event_types: b.event_types, is_active: b.is_active ?? true, created_at: new Date().toISOString(), retiring_secret_expires_at: null });
  }),
  http.patch("/api/v1/webhooks/configs/:id", async ({ request, params }) => HttpResponse.json({ ...fx.webhookConfigs[0], id: params.id as string, ...(await request.json() as object) })),
  http.delete("/api/v1/webhooks/configs/:id", () => HttpResponse.json(ok)),
  http.post("/api/v1/webhooks/configs/:id/rotate-secret", ({ params }) => HttpResponse.json({ ...fx.webhookConfigs[0], id: params.id as string, retiring_secret_expires_at: new Date(Date.now() + 86_400_000).toISOString() })),
  http.get("/api/v1/webhooks/configs/:id/deliveries", () => HttpResponse.json(fx.page(fx.webhookDeliveries))),

  // ---------------- connect ----------------
  http.post("/api/v1/connect/start", () => HttpResponse.json({ url: "https://connect.stripe.com/setup/mock" })),
  http.get("/api/v1/connect/status", () => HttpResponse.json({ connected: true, account_id: "acct_mock_123", charges_enabled: true, details_submitted: true })),

  // ---------------- sandbox ----------------
  http.post("/api/v1/sandbox/reset", () => HttpResponse.json({ status: "reset" })),

  // ---------------- audit ----------------
  http.get("/api/v1/audit/records", () => HttpResponse.json(fx.page(fx.auditRecords))),

  // ---------------- root ----------------
  http.get("/api/v1/customers/:id/past-limit-report", () => HttpResponse.json(fx.pastLimitReport)),
  http.get("/api/v1/health", () => HttpResponse.json({ status: "ok" })),
];
