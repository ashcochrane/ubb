// src/features/billing/api/api.ts
import type { MarginDashboardData, UpdateMarginRequest } from "./types";
import { billingApi } from "@/api/client";

export async function getMarginDashboard(): Promise<MarginDashboardData> {
  const { data } = await billingApi.GET("/margins", {});
  return data as MarginDashboardData;
}

export async function updateMargin(req: UpdateMarginRequest): Promise<{ success: boolean }> {
  const { data } = await billingApi.POST("/margins", { body: req });
  return data as { success: boolean };
}
