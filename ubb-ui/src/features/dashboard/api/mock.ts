// src/features/dashboard/api/mock.ts
import type { DashboardData } from "./types";
import { mockDashboardData } from "./mock-data";
import { mockDelay } from "@/lib/api-provider";

export async function getDashboard(): Promise<DashboardData> {
  await mockDelay();
  return structuredClone(mockDashboardData);
}
