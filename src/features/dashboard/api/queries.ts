import { useQuery } from "@tanstack/react-query";
import { dashboardApi } from "./provider";
import type { TimeRange } from "./types";

export const useDashboardStats = (range: TimeRange) =>
  useQuery({ queryKey: ["dashboard", "stats", range], queryFn: () => dashboardApi.getStats(range) });

export const useDashboardCharts = (range: TimeRange) =>
  useQuery({ queryKey: ["dashboard", "charts", range], queryFn: () => dashboardApi.getCharts(range) });

export const useDashboardCustomers = (range: TimeRange) =>
  useQuery({ queryKey: ["dashboard", "customers", range], queryFn: () => dashboardApi.getCustomers(range) });
