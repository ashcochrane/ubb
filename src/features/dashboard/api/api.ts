// src/features/dashboard/api/api.ts
import type { DashboardData } from "./types";
import { platformApi } from "@/api/client";

export async function getDashboard(): Promise<DashboardData> {
  const { data } = await platformApi.GET("/dashboard", {});
  return data as DashboardData;
}
