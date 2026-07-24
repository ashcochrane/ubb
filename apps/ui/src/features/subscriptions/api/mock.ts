// Mock provider — same exported signatures as api.ts, contract-correct
// responses, and coherent in-session mutation state (module-level `let`).

import { ApiProblem } from "@/api/problem";
import { mockDelay } from "@/lib/api-provider";

import { MOCK_CONNECT_STATUS, MOCK_PLANS, MOCK_SYNC_RESULT } from "./mock-data";
import type { ConnectStatus, PlanIn, PlanOut, PlanUpdateIn, SyncResponse } from "./types";

let plans: PlanOut[] = MOCK_PLANS.map((plan) => ({ ...plan }));

export async function getConnectStatus(): Promise<ConnectStatus> {
  await mockDelay();
  return { ...MOCK_CONNECT_STATUS };
}

export async function createPlan(input: PlanIn): Promise<PlanOut> {
  await mockDelay();
  if (plans.some((plan) => plan.key === input.key)) {
    throw new ApiProblem({
      status: 409,
      code: "conflict",
      title: "Conflict",
      detail: `A plan with key "${input.key}" already exists.`,
    });
  }
  const created: PlanOut = {
    id: crypto.randomUUID(),
    key: input.key,
    name: input.name,
    access_fee_micros: input.access_fee_micros,
    per_seat_micros: input.per_seat_micros,
    interval: input.interval,
  };
  plans = [...plans, created];
  return created;
}

export async function updatePlan(key: string, input: PlanUpdateIn): Promise<void> {
  await mockDelay();
  const existing = plans.find((plan) => plan.key === key);
  if (!existing) {
    throw new ApiProblem({
      status: 404,
      code: "not_found",
      title: "Not Found",
      detail: `No plan with key "${key}".`,
    });
  }
  plans = plans.map((plan) =>
    plan.key === key
      ? {
          ...plan,
          access_fee_micros: input.access_fee_micros ?? plan.access_fee_micros,
          per_seat_micros: input.per_seat_micros ?? plan.per_seat_micros,
        }
      : plan,
  );
}

export async function triggerSync(): Promise<SyncResponse> {
  await mockDelay(600);
  return { ...MOCK_SYNC_RESULT };
}
