// Representative fixture data for the MSW mock layer. Money is in integer
// micros (1 USD = 1_000_000). Enough breadth that every page renders with
// sensible, self-consistent data when VITE_API_PROVIDER=mock.

/** dollars → micros */
export const d = (dollars: number) => Math.round(dollars * 1_000_000);
const NOW = "2026-07-22T12:00:00Z";
const daysAgo = (n: number) =>
  new Date(Date.parse(NOW) - n * 86_400_000).toISOString();

/** Uniform cursor-page envelope (single page). */
export const page = <T>(data: T[]) => ({ data, next_cursor: null, has_more: false });

export const CUSTOMER_ID = "cus_mock_1";
export const EXTERNAL_ID = "acme-inc";

export const tenantConfig = {
  name: "Northwind Labs",
  billing_mode: "prepaid",
  products: ["metering", "billing", "subscriptions", "referrals"],
  require_cost_card_coverage: true,
  default_currency: "USD",
  stripe_connected_account_id: "acct_mock_123",
  is_active: true,
  automatic_tax_enabled: true,
  enforcement_mode: "monitor",
  arrival_signals_enabled: true,
  min_balance_micros: d(5),
  default_task_provider_cost_limit_micros: d(2),
  default_task_floor_snapshot_micros: d(1),
  soft_min_balance_micros: d(10),
};

export const balance = {
  balance_micros: d(1_284.5),
  currency: "USD",
  promo_micros: d(50),
  expiring_micros: d(25),
  next_expiry_at: daysAgo(-14),
  negative_since: null,
};

export const walletTransactions = [
  { id: "wtx_1", transaction_type: "top_up", amount_micros: d(500), balance_after_micros: d(1284.5), description: "Stripe top-up", reference_id: "pi_1", created_at: daysAgo(1) },
  { id: "wtx_2", transaction_type: "usage_debit", amount_micros: d(-42.18), balance_after_micros: d(784.5), description: "Usage for Jul 20", reference_id: "run_9", created_at: daysAgo(2) },
  { id: "wtx_3", transaction_type: "credit", amount_micros: d(100), balance_after_micros: d(826.68), description: "Goodwill credit", reference_id: "adj_3", created_at: daysAgo(5) },
  { id: "wtx_4", transaction_type: "grant", amount_micros: d(50), balance_after_micros: d(726.68), description: "Welcome grant", reference_id: "grant_1", created_at: daysAgo(9) },
];

export const grants = [
  { id: "grant_1", kind: "promotional", granted_micros: d(50), remaining_micros: d(32.4), expired_micros: 0, voided_micros: 0, currency: "USD", status: "active", source: "manual", expires_at: daysAgo(-21), warning_sent_at: null, created_at: daysAgo(9), balance_micros: d(32.4), transaction_id: "wtx_4" },
  { id: "grant_2", kind: "goodwill", granted_micros: d(25), remaining_micros: 0, expired_micros: d(25), voided_micros: 0, currency: "USD", status: "expired", source: "manual", expires_at: daysAgo(2), warning_sent_at: daysAgo(4), created_at: daysAgo(40), balance_micros: 0, transaction_id: "wtx_0" },
];

export const budgetConfig = { cap_micros: d(2000), enforce_mode: "monitor", hard_stop_pct: 100, alert_levels: [50, 80, 95], fail_closed: false };
export const budgetStatus = { period: "2026-07", spend_micros: d(842.18), cap_micros: d(2000), pct: 42.1, enforce_mode: "monitor" };
export const billingProfile = { min_balance_micros: d(5), topup_grant_expiry_days: 90, soft_min_balance_micros: d(10) };
export const postpaidConfig = { usage_line_item_group_by: "product", consolidate_with_subscription: false };

export const revenueAnalytics = {
  total_provider_cost_micros: d(4210.5),
  total_billed_cost_micros: d(6890.25),
  total_markup_micros: d(2679.75),
  daily: [
    { date: daysAgo(2), provider_cost_micros: d(140), billed_cost_micros: d(228), markup_micros: d(88) },
    { date: daysAgo(1), provider_cost_micros: d(162), billed_cost_micros: d(261), markup_micros: d(99) },
    { date: daysAgo(0), provider_cost_micros: d(155), billed_cost_micros: d(250), markup_micros: d(95) },
  ],
};

export const usageAnalytics = {
  total_events: 84_219,
  total_billed_cost_micros: d(6890.25),
  total_provider_cost_micros: d(4210.5),
  usage_markup_margin_micros: d(2679.75),
  by_provider: [
    { provider: "openai", event_count: 51_022, billed_cost_micros: d(4100), provider_cost_micros: d(2600) },
    { provider: "anthropic", event_count: 33_197, billed_cost_micros: d(2790.25), provider_cost_micros: d(1610.5) },
  ],
  by_event_type: [
    { event_type: "chat.completion", event_count: 70_120, billed_cost_micros: d(6010) },
    { event_type: "embedding", event_count: 14_099, billed_cost_micros: d(880.25) },
  ],
  by_customer: [
    { customer_id: CUSTOMER_ID, event_count: 40_000, billed_cost_micros: d(3200) },
    { customer_id: "cus_mock_2", event_count: 44_219, billed_cost_micros: d(3690.25) },
  ],
  by_product: [{ product_id: "assistant", event_count: 84_219, billed_cost_micros: d(6890.25) }],
  by_tag: [{ tag: "env:prod", event_count: 80_000 }],
  breakdowns: {},
};

export const usageTimeseries = {
  granularity: "day",
  group_by: "",
  series: [
    { date: daysAgo(2), events: 27_400, billed_cost_micros: d(2240) },
    { date: daysAgo(1), events: 29_100, billed_cost_micros: d(2380) },
    { date: daysAgo(0), events: 27_719, billed_cost_micros: d(2270.25) },
  ],
};

export const usageEvents = [
  { id: "evt_1", request_id: "req_1", event_type: "chat.completion", provider: "openai", provider_cost_micros: d(0.42), billed_cost_micros: d(0.68), units: 1240, metadata: { model: "gpt-4o" }, effective_at: daysAgo(0), stop_context: null },
  { id: "evt_2", request_id: "req_2", event_type: "embedding", provider: "anthropic", provider_cost_micros: d(0.02), billed_cost_micros: d(0.03), units: 512, metadata: {}, effective_at: daysAgo(1), stop_context: null },
];

export const usageEventDetail = {
  id: "evt_1", request_id: "req_1", idempotency_key: "idem_1", event_type: "chat.completion", provider: "openai",
  product_id: "assistant", service_id: "svc_1", agent_id: "agent_7", units: 1240, currency: "usd",
  provider_cost_micros: d(0.42), billed_cost_micros: d(0.68), usage_metrics: { input_tokens: 900, output_tokens: 340 },
  pricing_provenance: { rate_card: "book_1", rate: "rate_2" }, tags: { env: "prod" }, metadata: { model: "gpt-4o" },
  task_id: "task_1", effective_at: daysAgo(0), created_at: daysAgo(0), stop_context: null,
};

export const books = [
  { id: "book_1", card_type: "cost", provider_key: "openai", key: "openai-default", name: "OpenAI default", currency: "USD", version: 3, is_default: true },
  { id: "book_2", card_type: "cost", provider_key: "anthropic", key: "anthropic-default", name: "Anthropic default", currency: "USD", version: 1, is_default: false },
];

export const rates = [
  { id: "rate_1", rate_card_id: "book_1", lineage_id: "lin_1", card_type: "cost", metric_name: "input_tokens", provider: "openai", event_type: "chat.completion", dimensions: { model: "gpt-4o" }, pricing_model: "per_unit", rate_per_unit_micros: 5, unit_quantity: 1_000, fixed_micros: 0, currency: "USD", product_id: "assistant", valid_from: daysAgo(30), valid_to: null },
  { id: "rate_2", rate_card_id: "book_1", lineage_id: "lin_2", card_type: "cost", metric_name: "output_tokens", provider: "openai", event_type: "chat.completion", dimensions: { model: "gpt-4o" }, pricing_model: "per_unit", rate_per_unit_micros: 15, unit_quantity: 1_000, fixed_micros: 0, currency: "USD", product_id: "assistant", valid_from: daysAgo(30), valid_to: null },
];

export const tenantMarkup = { markup_percentage_micros: d(25), fixed_uplift_micros: 0 };

export const marginSummary = {
  period: { start: daysAgo(30), end: daysAgo(0) },
  subscription_revenue_micros: d(4800), usage_billed_micros: d(6890.25), usage_revenue_micros: d(2679.75),
  provider_cost_micros: d(4210.5), total_revenue_micros: d(9600), gross_margin_micros: d(5389.5),
  margin_percentage: 56.1, customer_count: 2,
};

export const marginList = {
  period: { start: daysAgo(30), end: daysAgo(0) },
  customers: [
    { customer_id: CUSTOMER_ID, subscription_revenue_micros: d(2400), usage_billed_micros: d(3200), usage_revenue_micros: d(1240), provider_cost_micros: d(1960), gross_margin_micros: d(2440), margin_percentage: 55.4 },
    { customer_id: "cus_mock_2", subscription_revenue_micros: d(2400), usage_billed_micros: d(3690.25), usage_revenue_micros: d(1439.75), provider_cost_micros: d(2250.5), gross_margin_micros: d(2949.5), margin_percentage: 56.7 },
  ],
};

export const customerMargin = {
  customer_id: CUSTOMER_ID, revenue_mode: "attributed", subscription_revenue_micros: d(2400), usage_billed_micros: d(3200),
  usage_revenue_micros: d(1240), provider_cost_micros: d(1960), total_revenue_micros: d(4800), gross_margin_micros: d(2440),
  margin_percentage: 55.4, event_count: 40_000, external_id: EXTERNAL_ID, period: { start: daysAgo(30), end: daysAgo(0) },
};

export const marginTrend = {
  customer_id: CUSTOMER_ID,
  points: [0, 1, 2, 3].map((i) => ({
    period_start: daysAgo((i + 1) * 30), provider_cost_micros: d(1800 + i * 40), usage_billed_micros: d(3000 + i * 60),
    subscription_revenue_micros: d(2400), gross_margin_micros: d(2300 + i * 30), margin_percentage: 54 + i,
  })),
};

export const revenueProfile = { recurring_amount_micros: d(200), interval: "month", currency: "usd", effective_from: daysAgo(60), effective_to: null };
export const revenueMode = { revenue_mode: "attributed", resolved: "attributed" };
export const marginByDimension = {
  period: { start: daysAgo(30), end: daysAgo(0) },
  rows: [
    { dimension: "openai", provider_cost_micros: d(2600), billed_cost_micros: d(4100), margin_micros: d(1500), event_count: 51_022 },
    { dimension: "anthropic", provider_cost_micros: d(1610.5), billed_cost_micros: d(2790.25), margin_micros: d(1179.75), event_count: 33_197 },
  ],
};
export const unprofitable = {
  period_start: daysAgo(30),
  customers: [{ customer_id: "cus_mock_3", external_id: "beta-co", gross_margin_micros: d(-120.5), margin_percentage: -8.2 }],
};
export const marginThreshold = { min_margin_pct: 20, consecutive_periods: 2, provider_cost_spike_pct: 25 };
export const businessMargin = {
  business_id: "biz_1", external_id: EXTERNAL_ID,
  totals: { subscription_revenue_micros: d(4800), usage_revenue_micros: d(2679.75), provider_cost_micros: d(4210.5), total_revenue_micros: d(9600), gross_margin_micros: d(5389.5), event_count: 84_219 },
  seats: [{ customer_id: CUSTOMER_ID, revenue_mode: "attributed", subscription_revenue_micros: d(2400), usage_billed_micros: d(3200), usage_revenue_micros: d(1240), provider_cost_micros: d(1960), total_revenue_micros: d(4800), gross_margin_micros: d(2440), margin_percentage: 55.4, event_count: 40_000 }],
};

export const subscription = {
  id: "sub_1", stripe_subscription_id: "sub_stripe_1", stripe_product_name: "Pro plan", status: "active",
  amount_micros: d(200), currency: "USD", interval: "month", current_period_start: daysAgo(10), current_period_end: daysAgo(-20), last_synced_at: daysAgo(0),
};
export const subscriptionInvoices = [
  { id: "sinv_1", stripe_invoice_id: "in_1", amount_paid_micros: d(200), currency: "USD", period_start: daysAgo(40), period_end: daysAgo(10), paid_at: daysAgo(38) },
  { id: "sinv_2", stripe_invoice_id: "in_2", amount_paid_micros: d(200), currency: "USD", period_start: daysAgo(70), period_end: daysAgo(40), paid_at: daysAgo(68) },
];

export const usageInvoices = [
  { period_start: daysAgo(30), period_end: daysAgo(0), total_billed_micros: d(6890.25), currency: "USD", status: "open", stripe_invoice_id: "in_usage_1", skip_reason: "", push_attempts: 1, last_attempt_error: null },
];
export const tenantUsageInvoices = [
  { customer_id: CUSTOMER_ID, external_id: EXTERNAL_ID, period_start: daysAgo(30), total_billed_micros: d(3200), status: "paid", stripe_invoice_id: "in_usage_1", skip_reason: "", push_attempts: 1, last_attempt_error: null },
  { customer_id: "cus_mock_2", external_id: "globex", period_start: daysAgo(30), total_billed_micros: d(3690.25), status: "open", stripe_invoice_id: "", skip_reason: "", push_attempts: 0, last_attempt_error: null },
];
export const tenantInvoices = [
  { id: "tinv_1", billing_period_id: "bp_1", stripe_invoice_id: "in_tenant_1", total_amount_micros: d(129), status: "paid", created_at: daysAgo(10) },
];
export const billingPeriods = [
  { id: "bp_1", period_start: daysAgo(60), period_end: daysAgo(30), status: "closed", total_usage_cost_micros: d(5900), event_count: 78_000, platform_fee_micros: d(129) },
  { id: "bp_2", period_start: daysAgo(30), period_end: daysAgo(0), status: "open", total_usage_cost_micros: d(6890.25), event_count: 84_219, platform_fee_micros: d(138) },
];

export const plan = { id: "plan_1", key: "pro", name: "Pro plan", access_fee_micros: d(200), per_seat_micros: d(15), interval: "month" };

export const program = {
  id: "prog_1", reward_type: "revenue_share", reward_value: 10, attribution_window_days: 30, reward_window_days: 90,
  max_reward_micros: d(500), estimated_cost_percentage: 30, max_referrals_per_day: 20, min_customer_age_hours: 24,
  status: "active", created_at: daysAgo(120), updated_at: daysAgo(3),
};
export const referrers = [
  { id: "ref_1", customer_id: CUSTOMER_ID, referral_code: "ACME10", referral_link_token: "tok_acme_abc123", is_active: true, created_at: daysAgo(90) },
  { id: "ref_2", customer_id: "cus_mock_2", referral_code: "GLOBEX5", referral_link_token: "tok_globex_def456", is_active: false, created_at: daysAgo(60) },
];
export const referrerEarnings = { referrer_customer_id: CUSTOMER_ID, total_earned_micros: d(320.5), total_referred_spend_micros: d(3205), total_referrals: 4, active_referrals: 3 };
export const referrals = [
  { id: "rfl_1", referred_customer_id: "cus_r1", referred_external_id: "startup-a", referral_code_used: "ACME10", status: "rewarded", reward_type: "revenue_share", total_earned_micros: d(120.5), total_referred_spend_micros: d(1205), attributed_at: daysAgo(40), reward_window_ends_at: daysAgo(-50) },
  { id: "rfl_2", referred_customer_id: "cus_r2", referred_external_id: "startup-b", referral_code_used: "ACME10", status: "attributed", reward_type: "revenue_share", total_earned_micros: d(0), total_referred_spend_micros: d(200), attributed_at: daysAgo(5), reward_window_ends_at: daysAgo(-85) },
];
export const ledgerEntries = [
  { id: "led_1", period_start: daysAgo(60), period_end: daysAgo(30), referred_spend_micros: d(1000), raw_cost_micros: d(600), reward_micros: d(100), calculation_method: "revenue_share", created_at: daysAgo(29) },
];
export const analyticsSummary = { total_referrers: 2, total_referrals: 4, active_referrals: 3, total_rewards_earned_micros: d(320.5), total_referred_spend_micros: d(3205) };
export const analyticsEarnings = {
  period_start: daysAgo(30), period_end: daysAgo(0), total_earned_micros: d(220.5),
  referrers: [{ referrer_customer_id: CUSTOMER_ID, external_id: EXTERNAL_ID, referral_code: "ACME10", total_earned_micros: d(220.5), referral_count: 4 }],
};
export const payoutExport = {
  data: [{ referrer_customer_id: CUSTOMER_ID, external_id: EXTERNAL_ID, referral_code: "ACME10", total_earned_micros: d(320.5), total_referred_spend_micros: d(3205), referral_count: 4, active_referral_count: 3 }],
  total_payout_micros: d(320.5), referrer_count: 1, exported_at: daysAgo(0),
};

export const webhookConfigs = [
  { id: "wh_1", url: "https://api.acme.com/hooks/ubb", event_types: ["usage.recorded", "stop.fired", "invoice.paid"], is_active: true, created_at: daysAgo(50), retiring_secret_expires_at: null },
  { id: "wh_2", url: "https://hooks.globex.io/ubb", event_types: ["balance.low"], is_active: false, created_at: daysAgo(20), retiring_secret_expires_at: daysAgo(-1) },
];
export const webhookDeliveries = [
  { id: "wd_1", event_id: "evt_a1", event_type: "usage.recorded", status_code: 200, success: true, error_message: "", created_at: daysAgo(0) },
  { id: "wd_2", event_id: "evt_a2", event_type: "stop.fired", status_code: 500, success: false, error_message: "upstream 500: internal error", created_at: daysAgo(1) },
];

export const apiKeys = [
  { id: "key_1", key_prefix: "sk_live_9x2", label: "Production", is_active: true, last_used_at: daysAgo(0), created_at: daysAgo(120) },
  { id: "key_2", key_prefix: "sk_test_4a1", label: "CI", is_active: true, last_used_at: daysAgo(3), created_at: daysAgo(30) },
];
export const members = [
  { id: "mem_1", email: "ash@northwind.dev", role: "owner", status: "active", clerk_user_id: "user_1", activated_at: daysAgo(200), created_at: daysAgo(200) },
  { id: "mem_2", email: "sam@northwind.dev", role: "admin", status: "active", clerk_user_id: "user_2", activated_at: daysAgo(90), created_at: daysAgo(95) },
];
export const invitations = [
  { id: "inv_1", email: "newhire@northwind.dev", role: "member", status: "pending", created_at: daysAgo(2) },
];

export const auditRecords = [
  { id: "aud_1", created_at: daysAgo(0), action: "wallet.credit", actor_kind: "user", actor_id: "user_1", actor_display: "ash@northwind.dev", resource_type: "wallet", resource_id: CUSTOMER_ID, correlation_id: "cor_1", metadata: { amount_micros: d(100), reason: "goodwill" } },
  { id: "aud_2", created_at: daysAgo(1), action: "webhook.created", actor_kind: "user", actor_id: "user_2", actor_display: "sam@northwind.dev", resource_type: "webhook", resource_id: "wh_1", correlation_id: "cor_2", metadata: { url: "https://api.acme.com/hooks/ubb" } },
];

export const pastLimitReport = {
  customer_id: CUSTOMER_ID, billing_owner_id: CUSTOMER_ID, since: daysAgo(30), until: daysAgo(0),
  episodes: [{ at: daysAgo(6), limit: "balance_floor", scope: "run" }],
  totals_per_limit: { balance_floor: 1, cost_limit: 0 },
};
