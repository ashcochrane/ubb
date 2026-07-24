// TanStack Query hooks over the provider. ALL query keys + invalidation for
// the billing feature live here. First key segment = backend namespace.

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useCursorList } from "@/api/pagination";

import { billingFeatureApi } from "./provider";
import type { BudgetConfigIn, CreditRequest, DebitRequest, PostpaidConfigIn } from "./types";

export const billingKeys = {
  all: ["billing"] as const,
  revenue: (range: { start_date: string; end_date: string }) =>
    ["billing", "revenue-analytics", range] as const,
  tenantBudget: ["billing", "budget", "tenant"] as const,
  tenantUsageInvoices: (period: string | null) =>
    ["billing", "tenant-usage-invoices", { period }] as const,
  postpaidConfig: ["billing", "postpaid-config"] as const,
};

export function useRevenueAnalytics(range: { start_date: string; end_date: string }) {
  return useQuery({
    queryKey: billingKeys.revenue(range),
    queryFn: () => billingFeatureApi.getRevenueAnalytics(range),
    // Window changes keep the previous chart visible instead of blanking.
    placeholderData: keepPreviousData,
  });
}

export function useTenantBudget() {
  return useQuery({
    queryKey: billingKeys.tenantBudget,
    queryFn: () => billingFeatureApi.getTenantBudget(),
  });
}

export function useTenantUsageInvoices(period: string | undefined) {
  return useCursorList(billingKeys.tenantUsageInvoices(period ?? null), (cursor) =>
    billingFeatureApi.listTenantUsageInvoices({ period, cursor }),
  );
}

export function usePostpaidConfig(enabled: boolean) {
  return useQuery({
    queryKey: billingKeys.postpaidConfig,
    queryFn: () => billingFeatureApi.getPostpaidConfig(),
    enabled,
  });
}

export function useSaveTenantBudget() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: BudgetConfigIn) => billingFeatureApi.putTenantBudget(body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: billingKeys.all });
    },
  });
}

export function useSavePostpaidConfig() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: PostpaidConfigIn) => billingFeatureApi.putPostpaidConfig(body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: billingKeys.all });
    },
  });
}

export function useCreditWallet() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreditRequest) => billingFeatureApi.creditWallet(body),
    onSuccess: () => {
      // Moves real money: over-invalidate the whole billing namespace so
      // balances/transactions elsewhere in the console refresh.
      void queryClient.invalidateQueries({ queryKey: billingKeys.all });
    },
  });
}

export function useDebitWallet() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: DebitRequest) => billingFeatureApi.debitWallet(body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: billingKeys.all });
    },
  });
}
