import { mockDelay } from "@/lib/api-provider";
import type { ChartsResponse, CustomersResponse, StatsResponse, TimeRange } from "./types";
import { mockCharts, mockCustomers, mockStats } from "./mock-data";

export async function getStats(_range: TimeRange): Promise<StatsResponse> {
  await mockDelay();
  return structuredClone(mockStats);
}

export async function getCharts(_range: TimeRange): Promise<ChartsResponse> {
  await mockDelay();
  return structuredClone(mockCharts);
}

export async function getCustomers(_range: TimeRange): Promise<CustomersResponse> {
  await mockDelay();
  return structuredClone(mockCustomers);
}
