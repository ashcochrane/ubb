// src/features/billing/api/mock.ts
import type { MarginDashboardData, UpdateMarginRequest } from "./types";
import { mockMarginData } from "./mock-data";
import { mockDelay } from "@/lib/api-provider";

export async function getMarginDashboard(): Promise<MarginDashboardData> {
  await mockDelay();
  return structuredClone(mockMarginData);
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export async function updateMargin(_req: UpdateMarginRequest): Promise<{ success: boolean }> {
  await mockDelay(500);
  return { success: true };
}
