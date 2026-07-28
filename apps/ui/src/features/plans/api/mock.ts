// Mock implementation — same exported signatures as api.ts, contract-correct
// shapes, coherent session-level mutation state (module-level `let`).

import { ApiProblem } from "@/api/problem";
import { mockDelay } from "@/lib/api-provider";

import { ASSIGNED_PLAN_KEYS, INITIAL_PLANS } from "./mock-data";
import type { Plan, PlanInput, PlanUpdateInput } from "./types";

let plans: Plan[] = INITIAL_PLANS.map((plan) => ({ ...plan }));
let idSeq = plans.length;

function problem(status: number, code: string, title: string, detail: string): ApiProblem {
  return new ApiProblem({ status, code, title, detail });
}

function requirePlan(key: string): Plan {
  const plan = plans.find((candidate) => candidate.key === key);
  if (!plan) {
    throw problem(404, "not_found", "Not found", `No plan with key "${key}".`);
  }
  return plan;
}

export async function listPlans(): Promise<{ plans: Plan[] }> {
  await mockDelay();
  return { plans: plans.map((plan) => ({ ...plan })) };
}

export async function createPlan(input: PlanInput): Promise<Plan> {
  await mockDelay();
  if (plans.some((plan) => plan.key === input.key)) {
    throw problem(
      409,
      "conflict",
      "Conflict",
      `A plan with key "${input.key}" already exists — keys must be unique.`,
    );
  }
  idSeq += 1;
  const created: Plan = {
    id: `plan_mock_${idSeq}`,
    key: input.key,
    name: input.name,
    access_fee_micros: input.access_fee_micros ?? 0,
    per_seat_micros: input.per_seat_micros ?? 0,
    markup_percentage_micros: input.markup_percentage_micros ?? 0,
    fixed_uplift_micros: input.fixed_uplift_micros ?? 0,
    interval: input.interval ?? "month",
    pricing_version: 1,
    archived_at: null,
  };
  plans = [...plans, created];
  return { ...created };
}

export async function updatePlan(key: string, input: PlanUpdateInput): Promise<Plan> {
  await mockDelay();
  const existing = requirePlan(key);
  // Mirrors update_plan_prices (subscriptions/orchestration/service.py): a
  // fee change mints a new Stripe price and bumps pricing_version; markup
  // changes apply immediately with no version bump — same story the plan
  // form dialog tells the user.
  const feeChanged =
    (input.access_fee_micros != null && input.access_fee_micros !== existing.access_fee_micros) ||
    (input.per_seat_micros != null && input.per_seat_micros !== existing.per_seat_micros);
  const updated: Plan = {
    ...existing,
    name: input.name ?? existing.name,
    access_fee_micros: input.access_fee_micros ?? existing.access_fee_micros,
    per_seat_micros: input.per_seat_micros ?? existing.per_seat_micros,
    markup_percentage_micros: input.markup_percentage_micros ?? existing.markup_percentage_micros,
    fixed_uplift_micros: input.fixed_uplift_micros ?? existing.fixed_uplift_micros,
    pricing_version: feeChanged ? existing.pricing_version + 1 : existing.pricing_version,
  };
  plans = plans.map((plan) => (plan.key === key ? updated : plan));
  return { ...updated };
}

export async function archivePlan(key: string): Promise<void> {
  await mockDelay();
  const plan = requirePlan(key);
  if (ASSIGNED_PLAN_KEYS.has(key)) {
    throw problem(
      409,
      "conflict",
      "Conflict",
      `Plan "${plan.key}" still has customers assigned — reassign them before archiving.`,
    );
  }
  const archived: Plan = { ...plan, archived_at: new Date().toISOString() };
  plans = plans.map((candidate) => (candidate.key === key ? archived : candidate));
}
