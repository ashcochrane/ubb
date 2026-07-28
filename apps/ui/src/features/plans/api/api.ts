// Real API calls for the tenant-level plans surface. The plan router is
// root-mounted at /api/v1/plans (not under /platform), so this uses the root
// client rather than the platformApi namespace.

import { rootApi } from "@/api/client";
import { unwrap } from "@/api/problem";

import type { Plan, PlanInput, PlanUpdateInput } from "./types";

/** GET /api/v1/plans */
export async function listPlans(): Promise<{ plans: Plan[] }> {
  return unwrap(await rootApi.GET("/plans"));
}

/** POST /api/v1/plans — 201 returns the provisioned plan; 409 on a duplicate key. */
export async function createPlan(input: PlanInput): Promise<Plan> {
  return unwrap(await rootApi.POST("/plans", { body: input }));
}

/** PATCH /api/v1/plans/{key} */
export async function updatePlan(key: string, input: PlanUpdateInput): Promise<Plan> {
  return unwrap(
    await rootApi.PATCH("/plans/{key}", {
      params: { path: { key } },
      body: input,
    }),
  );
}

/** DELETE /api/v1/plans/{key} — 409 while customers are still assigned. */
export async function archivePlan(key: string): Promise<void> {
  await unwrap(await rootApi.DELETE("/plans/{key}", { params: { path: { key } } }));
}
