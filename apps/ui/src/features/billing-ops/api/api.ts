// src/features/billing-ops/api/api.ts
import { billingApi } from "@/api/client";
import { requireData } from "@/api/errors";
import type { CursorPage } from "@/lib/use-cursor-list";
import type {
  Balance,
  ConfigureAutoTopUpRequest,
  CreateTopUpRequest,
  RefundRequest,
  TopUpCheckoutResponse,
  WalletTransaction,
  WithdrawRequest,
  WithdrawResponse,
} from "./types";

export function getBalance(customerId: string): Promise<Balance> {
  return billingApi
    .GET("/customers/{customer_id}/balance", {
      params: { path: { customer_id: customerId } },
    })
    .then((r) => requireData(r, "Failed to load balance"));
}

export function getTransactions(
  customerId: string,
  params?: { cursor?: string; limit?: number },
): Promise<CursorPage<WalletTransaction>> {
  return billingApi
    .GET("/customers/{customer_id}/transactions", {
      params: { path: { customer_id: customerId }, query: params },
    })
    .then((r) => requireData(r, "Failed to load transactions"));
}

export function createTopUp(
  customerId: string,
  body: CreateTopUpRequest,
): Promise<TopUpCheckoutResponse> {
  return billingApi
    .POST("/customers/{customer_id}/top-up", {
      params: { path: { customer_id: customerId } },
      body,
    })
    .then((r) => requireData(r, "Couldn't start top-up"));
}

export function withdraw(
  customerId: string,
  body: WithdrawRequest,
): Promise<WithdrawResponse> {
  return billingApi
    .POST("/customers/{customer_id}/withdraw", {
      params: { path: { customer_id: customerId } },
      body,
    })
    .then((r) => requireData(r, "Couldn't withdraw"));
}

export function refund(customerId: string, body: RefundRequest) {
  return billingApi
    .POST("/customers/{customer_id}/refund", {
      params: { path: { customer_id: customerId } },
      body,
    })
    .then((r) => requireData(r, "Couldn't refund"));
}

export function configureAutoTopUp(
  customerId: string,
  body: ConfigureAutoTopUpRequest,
) {
  return billingApi
    .PUT("/customers/{customer_id}/auto-top-up", {
      params: { path: { customer_id: customerId } },
      body,
    })
    .then((r) => requireData(r, "Couldn't configure auto top-up"));
}
