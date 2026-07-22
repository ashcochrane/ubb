// src/features/billing-ops/api/types.ts
import type { BillingSchemas } from "@/api/types";

export type Balance = BillingSchemas["BalanceResponse"];
export type WalletTransaction = BillingSchemas["WalletTransactionOut"];
export type CreateTopUpRequest = BillingSchemas["CreateTopUpRequest"];
export type TopUpCheckoutResponse = BillingSchemas["TopUpCheckoutResponse"];
export type WithdrawRequest = BillingSchemas["WithdrawRequest"];
export type WithdrawResponse = BillingSchemas["WithdrawResponse"];
export type RefundRequest = BillingSchemas["RefundRequest"];
export type ConfigureAutoTopUpRequest = BillingSchemas["ConfigureAutoTopUpRequest"];
