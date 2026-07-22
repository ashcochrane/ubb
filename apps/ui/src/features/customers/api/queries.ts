import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { toastOnError } from "@/lib/mutations";
import { useCursorList } from "@/lib/use-cursor-list";
import * as api from "./api";
import type {
  BillingProfileIn,
  BudgetConfigIn,
  CreateCustomerRequest,
  CreateGrantRequest,
  CustomerMarkupIn,
  RevenueModeIn,
  RevenueProfileIn,
  SeatsIn,
  SubscribeIn,
  SubscriptionCancelIn,
} from "./types";

const k = {
  roster: (from?: string, to?: string) => ["customers", "roster", from ?? "", to ?? ""] as const,
  margin: (id: string) => ["customers", id, "margin"] as const,
  trend: (id: string) => ["customers", id, "trend"] as const,
  revenue: (id: string) => ["customers", id, "revenue"] as const,
  revenueMode: (id: string) => ["customers", id, "revenue-mode"] as const,
  budget: (id: string) => ["customers", id, "budget"] as const,
  budgetStatus: (id: string) => ["customers", id, "budget-status"] as const,
  profile: (id: string) => ["customers", id, "billing-profile"] as const,
  markup: (id: string) => ["customers", id, "markup"] as const,
  grants: (id: string) => ["customers", id, "grants"] as const,
  usage: (id: string) => ["customers", id, "usage"] as const,
  subscription: (id: string) => ["customers", id, "subscription"] as const,
  subInvoices: (id: string) => ["customers", id, "subscription-invoices"] as const,
  business: (ext: string) => ["customers", "business", ext] as const,
  pastLimit: (id: string) => ["customers", id, "past-limit"] as const,
};

// ---- Roster / create ----
export function useMarginRoster(range?: { start_date?: string; end_date?: string }) {
  return useQuery({
    queryKey: k.roster(range?.start_date, range?.end_date),
    queryFn: () => api.listMarginCustomers(range),
  });
}

export function useCreateCustomer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateCustomerRequest) => api.createCustomer(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["customers", "roster"] });
      toast.success("Customer created");
    },
    onError: toastOnError("Couldn't create customer"),
  });
}

// ---- Margin ----
export const useCustomerMargin = (id: string) =>
  useQuery({ queryKey: k.margin(id), queryFn: () => api.getCustomerMargin(id), enabled: !!id });
export const useMarginTrend = (id: string) =>
  useQuery({ queryKey: k.trend(id), queryFn: () => api.getMarginTrend(id), enabled: !!id });
export const useRevenueProfile = (id: string) =>
  useQuery({ queryKey: k.revenue(id), queryFn: () => api.getRevenueProfile(id), enabled: !!id });
export const useRevenueMode = (id: string) =>
  useQuery({ queryKey: k.revenueMode(id), queryFn: () => api.getRevenueMode(id), enabled: !!id });

export function usePutRevenueProfile(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: RevenueProfileIn) => api.putRevenueProfile(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: k.revenue(id) });
      qc.invalidateQueries({ queryKey: k.margin(id) });
      toast.success("Revenue profile saved");
    },
    onError: toastOnError("Couldn't save revenue profile"),
  });
}
export function usePutRevenueMode(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: RevenueModeIn) => api.putRevenueMode(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: k.revenueMode(id) });
      qc.invalidateQueries({ queryKey: k.margin(id) });
      toast.success("Revenue mode saved");
    },
    onError: toastOnError("Couldn't save revenue mode"),
  });
}

// ---- Budget / profile / grants ----
export const useBudget = (id: string) =>
  useQuery({ queryKey: k.budget(id), queryFn: () => api.getBudget(id), enabled: !!id });
export const useBudgetStatus = (id: string) =>
  useQuery({ queryKey: k.budgetStatus(id), queryFn: () => api.getBudgetStatus(id), enabled: !!id });
export const useBillingProfile = (id: string) =>
  useQuery({ queryKey: k.profile(id), queryFn: () => api.getBillingProfile(id), enabled: !!id });
export const usePastLimitReport = (id: string) =>
  useQuery({ queryKey: k.pastLimit(id), queryFn: () => api.getPastLimitReport(id), enabled: !!id });

export function usePutBudget(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: BudgetConfigIn) => api.putBudget(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: k.budget(id) });
      qc.invalidateQueries({ queryKey: k.budgetStatus(id) });
      toast.success("Budget saved");
    },
    onError: toastOnError("Couldn't save budget"),
  });
}
export function usePutBillingProfile(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: BillingProfileIn) => api.putBillingProfile(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: k.profile(id) });
      toast.success("Billing profile saved");
    },
    onError: toastOnError("Couldn't save billing profile"),
  });
}

export function useGrants(id: string, status?: string) {
  return useCursorList({
    queryKeyBase: [...k.grants(id), status ?? "all"],
    fetchPage: (cursor) => api.listGrants(id, { status, cursor, limit: 50 }),
    enabled: !!id,
  });
}
export function useCreateGrant(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateGrantRequest) => api.createGrant(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: k.grants(id) });
      toast.success("Grant created");
    },
    onError: toastOnError("Couldn't create grant"),
  });
}
export function useVoidGrant(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (grantId: string) => api.voidGrant(id, grantId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: k.grants(id) });
      toast.success("Grant voided");
    },
    onError: toastOnError("Couldn't void grant"),
  });
}

// ---- Markup / rate card ----
export const useCustomerMarkup = (id: string) =>
  useQuery({ queryKey: k.markup(id), queryFn: () => api.getCustomerMarkup(id), enabled: !!id });

export function usePutCustomerMarkup(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: CustomerMarkupIn) => api.putCustomerMarkup(id, body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: k.markup(id) });
      toast.success("Markup override saved");
    },
    onError: toastOnError("Couldn't save markup"),
  });
}
export function useDeleteCustomerMarkup(id: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.deleteCustomerMarkup(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: k.markup(id) });
      toast.success("Markup override removed");
    },
    onError: toastOnError("Couldn't remove markup"),
  });
}
export function useAssignRateCard(id: string) {
  return useMutation({
    mutationFn: (rate_card_id: string) => api.assignRateCard(id, { rate_card_id }),
    onSuccess: () => toast.success("Rate card assigned"),
    onError: toastOnError("Couldn't assign rate card"),
  });
}

// ---- Usage ----
export function useCustomerUsage(id: string) {
  return useCursorList({
    queryKeyBase: k.usage(id),
    fetchPage: (cursor) => api.listCustomerUsage(id, { cursor, limit: 50 }),
    enabled: !!id,
  });
}

// ---- Subscription ----
export const useSubscription = (id: string) =>
  useQuery({ queryKey: k.subscription(id), queryFn: () => api.getSubscription(id), enabled: !!id, retry: 0 });
export function useSubscriptionInvoices(id: string) {
  return useCursorList({
    queryKeyBase: k.subInvoices(id),
    fetchPage: (cursor) => api.listSubscriptionInvoices(id, { cursor, limit: 50 }),
    enabled: !!id,
  });
}

function useSubLifecycle<TArgs>(
  id: string,
  fn: (args: TArgs) => Promise<unknown>,
  success: string,
  failure: string,
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: k.subscription(id) });
      toast.success(success);
    },
    onError: toastOnError(failure),
  });
}

export const useSubscribeCustomer = (id: string, externalId: string) =>
  useSubLifecycle<SubscribeIn>(id, (b) => api.subscribeCustomer(externalId, b), "Subscription started", "Couldn't subscribe");
export const useSetSeats = (id: string, externalId: string) =>
  useSubLifecycle<SeatsIn>(id, (b) => api.setSeats(externalId, b), "Seats updated", "Couldn't set seats");
export const useCancelSubscription = (id: string, externalId: string) =>
  useSubLifecycle<SubscriptionCancelIn | undefined>(id, (b) => api.cancelSubscription(externalId, b), "Subscription canceled", "Couldn't cancel");
export const usePauseSubscription = (id: string, externalId: string) =>
  useSubLifecycle<void>(id, () => api.pauseSubscription(externalId), "Subscription paused", "Couldn't pause");
export const useResumeSubscription = (id: string, externalId: string) =>
  useSubLifecycle<void>(id, () => api.resumeSubscription(externalId), "Subscription resumed", "Couldn't resume");
