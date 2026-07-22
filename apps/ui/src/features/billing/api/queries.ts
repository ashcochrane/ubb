// src/features/billing/api/queries.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { formatMicros } from "@/lib/format";
import { toastOnError } from "@/lib/mutations";
import { useCursorList } from "@/lib/use-cursor-list";
import * as api from "./api";
import type {
  BudgetConfigIn,
  CreditRequest,
  DateRange,
  DebitRequest,
  PostpaidConfigIn,
  PreCheckRequest,
} from "./types";

const budgetKey = ["billing", "budget"] as const;
const postpaidKey = ["billing", "postpaid-config"] as const;
const revenueKey = (range: DateRange) =>
  ["billing", "revenue", range.start_date ?? "", range.end_date ?? ""] as const;
const usageInvoicesKey = (period?: string) =>
  ["billing", "tenant-usage-invoices", period ?? "all"] as const;
const tenantInvoicesKey = ["billing", "tenant-invoices"] as const;
const billingPeriodsKey = ["billing", "billing-periods"] as const;

// --- Tenant budget ---
export function useBudget() {
  return useQuery({ queryKey: budgetKey, queryFn: api.getBudget });
}

export function usePutBudget() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: BudgetConfigIn) => api.putBudget(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: budgetKey });
      toast.success("Tenant budget saved");
    },
    onError: toastOnError("Couldn't save budget"),
  });
}

// --- Postpaid config ---
export function usePostpaidConfig() {
  return useQuery({ queryKey: postpaidKey, queryFn: api.getPostpaidConfig });
}

export function usePutPostpaidConfig() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: PostpaidConfigIn) => api.putPostpaidConfig(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: postpaidKey });
      toast.success("Postpaid config saved");
    },
    onError: toastOnError("Couldn't save postpaid config"),
  });
}

// --- Revenue analytics ---
export function useRevenueAnalytics(range: DateRange) {
  return useQuery({
    queryKey: revenueKey(range),
    queryFn: () => api.getRevenueAnalytics(range),
  });
}

// --- Manual adjustments ---
export function useCredit() {
  return useMutation({
    mutationFn: (body: CreditRequest) => api.credit(body),
    onSuccess: (data) =>
      toast.success("Credit issued", {
        description: `New wallet balance: ${formatMicros(data.new_balance_micros)}`,
      }),
    onError: toastOnError("Couldn't issue credit"),
  });
}

export function useDebit() {
  return useMutation({
    mutationFn: (body: DebitRequest) => api.debit(body),
    onSuccess: (data) =>
      toast.success("Debit recorded", {
        description: `New wallet balance: ${formatMicros(data.new_balance_micros)}`,
      }),
    onError: toastOnError("Couldn't record debit"),
  });
}

// --- Spend pre-check ---
export function usePreCheck() {
  return useMutation({
    mutationFn: (body: PreCheckRequest) => api.preCheck(body),
    onError: toastOnError("Pre-check failed"),
  });
}

// --- Invoices & periods ---
export function useTenantUsageInvoices(period?: string) {
  return useCursorList({
    queryKeyBase: usageInvoicesKey(period),
    fetchPage: (cursor) =>
      api.listTenantUsageInvoices({ period, cursor, limit: 50 }),
  });
}

export function useTenantInvoices() {
  return useCursorList({
    queryKeyBase: tenantInvoicesKey,
    fetchPage: (cursor) => api.listTenantInvoices({ cursor, limit: 50 }),
  });
}

export function useBillingPeriods() {
  return useCursorList({
    queryKeyBase: billingPeriodsKey,
    fetchPage: (cursor) => api.listBillingPeriods({ cursor, limit: 50 }),
  });
}
