// src/features/billing-ops/api/api.ts
import { billingApi } from "@/api/client";
import type {
  Balance,
  BillingTransaction,
  ConfigureAutoTopUpRequest,
  CreateTopUpRequest,
  RefundRequest,
  TransactionsPage,
  WithdrawRequest,
} from "./types";

export async function getBalance(customerId: string): Promise<Balance> {
  const { data, error } = await billingApi.GET(
    "/customers/{customer_id}/balance",
    { params: { path: { customer_id: customerId } } },
  );
  if (error || !data) throw error ?? new Error("Failed to load balance");
  return data;
}

export async function getTransactions(
  customerId: string,
  params?: { cursor?: string; limit?: number },
): Promise<TransactionsPage> {
  const { data, error } = await billingApi.GET(
    "/customers/{customer_id}/transactions",
    {
      params: { path: { customer_id: customerId }, query: params },
    },
  );
  if (error) throw error;
  return normalizeTransactionsPage(data);
}

export async function createTopUp(
  customerId: string,
  body: CreateTopUpRequest,
): Promise<void> {
  const { error } = await billingApi.POST(
    "/customers/{customer_id}/top-up",
    {
      params: { path: { customer_id: customerId } },
      body,
    },
  );
  if (error) throw error;
}

export async function withdraw(
  customerId: string,
  body: WithdrawRequest,
): Promise<void> {
  const { error } = await billingApi.POST(
    "/customers/{customer_id}/withdraw",
    {
      params: { path: { customer_id: customerId } },
      body,
    },
  );
  if (error) throw error;
}

export async function refund(
  customerId: string,
  body: RefundRequest,
): Promise<void> {
  const { error } = await billingApi.POST(
    "/customers/{customer_id}/refund",
    {
      params: { path: { customer_id: customerId } },
      body,
    },
  );
  if (error) throw error;
}

export async function configureAutoTopUp(
  customerId: string,
  body: ConfigureAutoTopUpRequest,
): Promise<void> {
  const { error } = await billingApi.PUT(
    "/customers/{customer_id}/auto-top-up",
    {
      params: { path: { customer_id: customerId } },
      body,
    },
  );
  if (error) throw error;
}

// The backend endpoint has no typed response schema. To keep this surface
// resilient (and to make the eventual schema-add a no-op), we accept any of:
//   • `{ data, hasMore, nextCursor }` (current/most-likely shape)
//   • a raw array of transaction-ish objects
//   • undefined / null
// and drop rows that fail a minimal sanity check. The moment the backend
// ships a response_model annotation, regenerate types, type
// `BillingTransaction` from `BillingSchemas`, and inline this away.
function normalizeTransactionsPage(input: unknown): TransactionsPage {
  if (input == null) return { data: [], hasMore: false, nextCursor: null };
  const obj = input as Record<string, unknown>;
  const rawRows = Array.isArray(input)
    ? (input as unknown[])
    : Array.isArray(obj.data)
      ? (obj.data as unknown[])
      : [];
  const rows = rawRows
    .map(normalizeTransaction)
    .filter((r): r is BillingTransaction => r !== null);
  return {
    data: rows,
    hasMore: typeof obj.hasMore === "boolean" ? obj.hasMore : false,
    nextCursor:
      typeof obj.nextCursor === "string" || obj.nextCursor === null
        ? (obj.nextCursor as string | null)
        : null,
  };
}

function normalizeTransaction(row: unknown): BillingTransaction | null {
  if (!row || typeof row !== "object") return null;
  const r = row as Record<string, unknown>;
  if (typeof r.id !== "string") return null;
  if (typeof r.amountMicros !== "number") return null;
  return {
    id: r.id,
    type: typeof r.type === "string" ? r.type : "",
    amountMicros: r.amountMicros,
    balanceAfterMicros:
      typeof r.balanceAfterMicros === "number" ? r.balanceAfterMicros : 0,
    description: typeof r.description === "string" ? r.description : "",
    createdAt: typeof r.createdAt === "string" ? r.createdAt : "",
  };
}
