import { useQuery } from "@tanstack/react-query";
import * as api from "./api";
import type { DateRange } from "./types";

const KEY = "overview" as const;

export const useMarginSummary = (range: DateRange) =>
  useQuery({
    queryKey: [KEY, "margin-summary", range],
    queryFn: () => api.getMarginSummary(range),
  });

export const useUnprofitable = () =>
  useQuery({
    queryKey: [KEY, "unprofitable"],
    queryFn: () => api.getUnprofitable(),
  });

export const useRevenueAnalytics = (range: DateRange) =>
  useQuery({
    queryKey: [KEY, "revenue", range],
    queryFn: () => api.getRevenueAnalytics(range),
  });

export const useBudget = () =>
  useQuery({
    queryKey: [KEY, "budget"],
    queryFn: () => api.getBudget(),
  });

export const useUsageAnalytics = (range: DateRange) =>
  useQuery({
    queryKey: [KEY, "usage", range],
    queryFn: () => api.getUsageAnalytics(range),
  });

export const useWebhookConfigs = () =>
  useQuery({
    queryKey: [KEY, "webhook-configs"],
    queryFn: () => api.listWebhookConfigs(),
  });
