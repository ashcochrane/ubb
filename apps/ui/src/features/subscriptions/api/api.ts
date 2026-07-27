import { platformApi, subscriptionsApi } from "@/api/client";
import { requireData } from "@/api/errors";
import type { CursorPage } from "@/lib/use-cursor-list";
import type {
  PlanIn,
  PlanOut,
  PlanUpdateIn,
  StripeSubscription,
  SubscriptionInvoice,
  SyncResponse,
} from "./types";

/** Reconcile subscriptions from Stripe. No body; returns per-record counts. */
export function syncSubscriptions(): Promise<SyncResponse> {
  return subscriptionsApi
    .POST("/sync", {})
    .then((r) => requireData(r, "Failed to sync subscriptions from Stripe"));
}

/** Read the single active subscription for one customer. 404 when none exists. */
export function getCustomerSubscription(
  customerId: string,
): Promise<StripeSubscription> {
  return subscriptionsApi
    .GET("/customers/{customer_id}/subscription", {
      params: { path: { customer_id: customerId } },
    })
    .then((r) => requireData(r, "Failed to load subscription"));
}

export function listCustomerInvoices(
  customerId: string,
  params?: { cursor?: string; limit?: number },
): Promise<CursorPage<SubscriptionInvoice>> {
  return subscriptionsApi
    .GET("/customers/{customer_id}/invoices", {
      params: { path: { customer_id: customerId }, query: params },
    })
    .then((r) => requireData(r, "Failed to load subscription invoices"));
}

/** Create a plan (blind — there is no list-plans endpoint). Keyed by `key`. */
export function createPlan(body: PlanIn): Promise<PlanOut> {
  return platformApi
    .POST("/plans", { body })
    .then((r) => requireData(r, "Failed to create plan"));
}

/** Re-price an existing plan by key. Returns an untyped object on success. */
export function updatePlan(
  key: string,
  body: PlanUpdateIn,
): Promise<Record<string, unknown>> {
  return platformApi
    .PATCH("/plans/{key}", { params: { path: { key } }, body })
    .then((r) => requireData(r, "Failed to update plan"));
}
