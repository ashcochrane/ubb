import type { PlatformSchemas, SubscriptionSchemas } from "@/api/types";

// Subscriptions namespace (`/api/v1/subscriptions`).
export type SyncResponse = SubscriptionSchemas["SyncResponse"];
export type StripeSubscription = SubscriptionSchemas["StripeSubscriptionOut"];
export type SubscriptionInvoice = SubscriptionSchemas["SubscriptionInvoiceOut"];

// Plans live on the platform namespace (`/api/v1/platform`).
export type PlanIn = PlatformSchemas["PlanIn"];
export type PlanOut = PlatformSchemas["PlanOut"];
export type PlanUpdateIn = PlatformSchemas["PlanUpdateIn"];
