// Mock implementation — same exported signatures as api.ts, contract-correct
// shapes, coherent session-level mutation state (module-level `let`).

import { ApiProblem } from "@/api/problem";
import { mockDelay } from "@/lib/api-provider";
import { measuresFor } from "@/lib/economic-scenarios";

import {
  SEAT_DEFAULT_POOL,
  INITIAL_POSTPAID_CONFIG,
  INITIAL_WALLETS,
  TENANT_USAGE_INVOICES,
  buildDailyRows,
  rowsInRange,
  type MockDailyRow,
} from "./mock-data";
import type {
  CustomerSpendPool,
  CustomerSpendPoolIn,
  CreditRequest,
  DebitCreditResponse,
  DebitRequest,
  PostpaidConfig,
  PostpaidConfigIn,
  Economics,
  TenantUsageInvoicePage,
} from "./types";

let seatDefaultPool: CustomerSpendPool = {
  ...SEAT_DEFAULT_POOL,
  alert_levels: [...SEAT_DEFAULT_POOL.alert_levels],
};
let postpaidConfig: PostpaidConfig = { ...INITIAL_POSTPAID_CONFIG };
const wallets: Record<string, number> = { ...INITIAL_WALLETS };
// Replay-safety: idempotency_key → the original answer.
const ledgerReplays = new Map<string, DebitCreditResponse>();
let transactionSeq = 4200;

const ALL_DAILY_ROWS = buildDailyRows();

export async function getRevenueWindow(range: {
  start_date?: string;
  end_date?: string;
}): Promise<Economics> {
  await mockDelay();
  const daily = rowsInRange(ALL_DAILY_ROWS, range);
  return {
    period_start: range.start_date ?? "",
    period_end: range.end_date ?? "",
    group_by: [],
    bucket: "day",
    basis: "recorded",
    economic_data_available_from: "2020-07-01",
    measurement_data_available_from: "2026-01-01",
    // ⚠ THE WINDOW'S TOTALS ARE NOT A FIELD ANY MORE, AND THAT IS THE POINT.
    // The report this replaced published its own totals beside its day rows,
    // which was a second definition of the same sum; the one query answers the
    // buckets and the console adds them up, so the two cannot disagree.
    //
    // ⚠ AND EACH DAY'S STATES ARE COMPOSED, NOT WRITTEN (#510). This wrote the
    // margin's state from the cost side alone, which is §15's rule stated
    // halfway: the query derives it from BOTH sides. The composers derive it.
    rows: daily.map((row) => ({
      bucket_start: `${row.day}T00:00:00+00:00`,
      grouping_field_value: [],
      grouping_field_value_status: [],
      measures: measuresForDay(row),
    })),
    context: [],
  };
}

/** One fixture day's four measures, as the query would state them. */
function measuresForDay(row: MockDailyRow) {
  return measuresFor({
    cost_micros: row.provider_cost_micros,
    revenue_micros: row.revenue_micros,
    events: row.event_count,
    unresolved_event_count: row.unresolved_event_count,
    unpriced_event_count: row.unpriced_event_count,
  });
}

export async function getTenantCustomerSpendPool(): Promise<CustomerSpendPool> {
  await mockDelay();
  return { ...seatDefaultPool, alert_levels: [...seatDefaultPool.alert_levels] };
}

export async function putTenantCustomerSpendPool(body: CustomerSpendPoolIn): Promise<CustomerSpendPool> {
  await mockDelay();
  // Full upsert with schema defaults — mirrors the server precisely.
  seatDefaultPool = {
    cap_micros: body.cap_micros,
    enforce_mode: body.enforce_mode ?? "alert_only",
    hard_stop_pct: body.hard_stop_pct ?? 100,
    alert_levels: body.alert_levels ? [...body.alert_levels] : [],
    fail_closed: body.fail_closed ?? false,
  };
  return { ...seatDefaultPool, alert_levels: [...seatDefaultPool.alert_levels] };
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
    group_by:
      body.group_by ?? postpaidConfig.group_by,
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
