// src/features/dashboard/api/mock.ts
import type { DashboardData } from "./types";
import { mockDashboardData } from "./mock-data";

const delay = (ms = 300) => new Promise((r) => setTimeout(r, ms));

export async function getDashboard(): Promise<DashboardData> {
  await delay();
  return structuredClone(mockDashboardData);
}
