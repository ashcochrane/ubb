// Real API calls for the tenant-level subscriptions surface.

import { connectApi, platformApi, subscriptionsApi } from "@/api/client";
import { unwrap } from "@/api/problem";

import {
  toConnectStatus,
  type ConnectStatus,
  type PlanIn,
  type PlanOut,
  type PlanUpdateIn,
  type SyncResponse,
} from "./types";

/** GET /api/v1/connect/status — Stripe Connect onboarding state (read floor). */
export async function getConnectStatus(): Promise<ConnectStatus> {
  return toConnectStatus(unwrap(await connectApi.GET("/status")));
}

/** POST /api/v1/platform/plans — 201 returns the provisioned plan; 409 on a duplicate key. */
export async function createPlan(input: PlanIn): Promise<PlanOut> {
  return unwrap(await platformApi.POST("/plans", { body: input }));
}

/**
 * PATCH /api/v1/platform/plans/{key} — 200 body is untyped in the contract
 * (unlike create's PlanOut), so treat it as a bare acknowledgement; 404 on an
 * unknown key.
 */
export async function updatePlan(key: string, input: PlanUpdateIn): Promise<void> {
  unwrap(await platformApi.PATCH("/plans/{key}", { params: { path: { key } }, body: input }));
}

/** POST /api/v1/subscriptions/sync — synchronous; returns {synced, skipped, errors} counts. */
export async function triggerSync(): Promise<SyncResponse> {
  return unwrap(await subscriptionsApi.POST("/sync"));
}
