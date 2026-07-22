// src/features/billing-ops/api/types.ts
import type { BillingSchemas } from "@/api/types";

export type Balance = BillingSchemas["BalanceResponse"];
export type CreateTopUpRequest = BillingSchemas["CreateTopUpRequest"];
export type WithdrawRequest = BillingSchemas["WithdrawRequest"];
export type RefundRequest = BillingSchemas["RefundRequest"];
export type ConfigureAutoTopUpRequest =
  BillingSchemas["ConfigureAutoTopUpRequest"];

// /customers/{id}/transactions has no typed response schema in openapi.
// Shape mirrors what the WalletTransaction serializer returns. If the backend
// adds a schema, regenerate and replace this type with the generated one.
export interface BillingTransaction {
  id: string;
  type: string;
  amountMicros: number;
  balanceAfterMicros: number;
  description: string;
  createdAt: string;
}

export interface TransactionsPage {
  data: BillingTransaction[];
  hasMore: boolean;
  nextCursor: string | null;
}
