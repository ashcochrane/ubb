// Mock implementation — same exported signatures as api.ts, contract-correct
// shapes, coherent session-level mutation state (module-level `let`).

import { ApiProblem } from "@/api/problem";
import { mockDelay } from "@/lib/api-provider";

import {
  INITIAL_BUDGET,
  INITIAL_POSTPAID_CONFIG,
  INITIAL_WALLETS,
  TENANT_USAGE_INVOICES,
  buildDailyRows,
  rowsInRange,
} from "./mock-data";
import type {
  BudgetConfig,
  BudgetConfigIn,
  CreditRequest,
  DebitCreditResponse,
  DebitRequest,
  PostpaidConfig,
  PostpaidConfigIn,
  RevenueAnalyticsResponse,
  TenantUsageInvoicePage,
} from "./types";

let budget: BudgetConfig = { ...INITIAL_BUDGET, alert_levels: [...INITIAL_BUDGET.alert_levels] };
let postpaidConfig: PostpaidConfig = { ...INITIAL_POSTPAID_CONFIG };
const wallets: Record<string, number> = { ...INITIAL_WALLETS };
// Replay-safety: idempotency_key → the original answer.
const ledgerReplays = new Map<string, DebitCreditResponse>();
let transactionSeq = 4200;

const ALL_DAILY_ROWS = buildDailyRows();

export async function getRevenueAnalytics(range: {
  start_date?: string;
  end_date?: string;
}): Promise<RevenueAnalyticsResponse> {
  await mockDelay();
  const daily = rowsInRange(ALL_DAILY_ROWS, range);
  const totalProvider = daily.reduce((sum, row) => sum + row.provider_cost_micros, 0);
  const totalBilled = daily.reduce((sum, row) => sum + row.billed_cost_micros, 0);
  return {
    // The real endpoint returns untyped objects here; spreading keeps the
    // mock honest about that shape.
    daily: daily.map((row) => ({ ...row })),
    total_provider_cost_micros: totalProvider,
    // SUMMED FROM THE ROWS RATHER THAN STATED (#330). The window's count is
    // the sum of its days' counts on the server too, so a mock that wrote its
    // own would be a second definition — and would go on saying "nothing was
    // excluded" whatever the rows said. The fixture puts uncosted events on
    // today, so every window ending today is partial and the tiles below it
    // read "at least".
    unresolved_event_count: daily.reduce(
      (sum, row) => sum + row.unresolved_event_count,
      0,
    ),
    total_billed_cost_micros: totalBilled,
    total_markup_micros: totalBilled - totalProvider,
  };
}

export async function getTenantBudget(): Promise<BudgetConfig> {
  await mockDelay();
  return { ...budget, alert_levels: [...budget.alert_levels] };
}

export async function putTenantBudget(body: BudgetConfigIn): Promise<BudgetConfig> {
  await mockDelay();
  // Full upsert with schema defaults — mirrors the server precisely.
  budget = {
    cap_micros: body.cap_micros,
    enforce_mode: body.enforce_mode ?? "alert_only",
    hard_stop_pct: body.hard_stop_pct ?? 100,
    alert_levels: body.alert_levels ? [...body.alert_levels] : [],
    fail_closed: body.fail_closed ?? false,
  };
  return { ...budget, alert_levels: [...budget.alert_levels] };
}

export async function listTenantUsageInvoices(options: {
  period?: string;
  cursor?: string;
}): Promise<TenantUsageInvoicePage> {
  await mockDelay();
  const rows = TENANT_USAGE_INVOICES.filter(
    (invoice) => !options.period || invoice.period_start === options.period,
  );
  return { data: rows.map((row) => ({ ...row })), has_more: false, next_cursor: null };
}

export async function getPostpaidConfig(): Promise<PostpaidConfig> {
  await mockDelay();
  return { ...postpaidConfig };
}

export async function putPostpaidConfig(body: PostpaidConfigIn): Promise<PostpaidConfig> {
  await mockDelay();
  // PARTIAL semantics: omitted/null preserves; explicit "" clears group-by.
  postpaidConfig = {
    usage_line_item_group_by:
      body.usage_line_item_group_by ?? postpaidConfig.usage_line_item_group_by,
    consolidate_with_subscription:
      body.consolidate_with_subscription ?? postpaidConfig.consolidate_with_subscription,
  };
  return { ...postpaidConfig };
}

function applyLedgerAdjustment(
  externalId: string,
  deltaMicros: number,
  idempotencyKey: string,
  allowNegative: boolean,
): DebitCreditResponse {
  const replay = ledgerReplays.get(idempotencyKey);
  if (replay) return { ...replay };
  const current = wallets[externalId];
  if (current === undefined) {
    throw new ApiProblem({
      status: 404,
      code: "not_found",
      title: "Customer not found",
      detail: `No customer with external id "${externalId}".`,
    });
  }
  const next = current + deltaMicros;
  if (next < 0 && !allowNegative) {
    throw new ApiProblem({
      status: 409,
      code: "insufficient_balance",
      title: "Insufficient balance",
      detail: `The balance would go negative. Enable "allow negative" to permit an overdraft.`,
    });
  }
  wallets[externalId] = next;
  transactionSeq += 1;
  const response: DebitCreditResponse = {
    transaction_id: `txn_mock_${transactionSeq}`,
    new_balance_micros: next,
  };
  ledgerReplays.set(idempotencyKey, response);
  return { ...response };
}

export async function creditWallet(body: CreditRequest): Promise<DebitCreditResponse> {
  await mockDelay();
  return applyLedgerAdjustment(body.customer_id, body.amount_micros, body.idempotency_key, true);
}

export async function debitWallet(body: DebitRequest): Promise<DebitCreditResponse> {
  await mockDelay();
  return applyLedgerAdjustment(
    body.customer_id,
    -body.amount_micros,
    body.idempotency_key,
    body.allow_negative ?? false,
  );
}
