import { platformApi } from "@/api/client";
import type {
  ChartsResponse, CustomersResponse, StatsResponse, TimeRange,
} from "./types";

export async function getStats(range: TimeRange): Promise<StatsResponse> {
  const { data } = await platformApi.GET("/dashboard/stats", {
    params: { query: { range } },
  });
  return data as StatsResponse;
}

export async function getCharts(range: TimeRange): Promise<ChartsResponse> {
  const { data } = await platformApi.GET("/dashboard/charts", {
    params: { query: { range } },
  });
  return data as ChartsResponse;
}

export async function getCustomers(range: TimeRange): Promise<CustomersResponse> {
  const { data } = await platformApi.GET("/dashboard/customers", {
    params: { query: { range } },
  });
  return data as CustomersResponse;
}
