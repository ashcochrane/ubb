// TanStack Query hooks over the provider. ALL query keys and invalidation
// live here (first key segment = backend namespace, not feature name).
//
// 404-as-state reads (revenue profile / business rollup / subscription) are
// caught in the queryFn and resolved to null so an expected absence never
// retries or renders as an error.

import {
  keepPreviousData,
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { useCursorList } from "@/api/pagination";
import { isNotFound } from "@/api/problem";
import type { DateRange } from "@/lib/date-range";

import { customersApi } from "./provider";
import type {
  BudgetConfigIn,
  ConfigureAutoTopUpRequest,
  CreateCustomerRequest,
  CreateGrantRequest,
  CreateTopUpRequest,
  CreditRequest,
  CustomerBillingProfileIn,
  DebitRequest,
  RevenueProfileIn,
  SubscribeIn,
  TenantMarkupIn,
  WithdrawRequest,
} from "./types";

async function nullOn404<T>(promise: Promise<T>): Promise<T | null> {
  try {
    return await promise;
  } catch (error) {
    if (isNotFound(error)) return null;
    throw error;
  }
}

// ---------------------------------------------------------------------------
// Margin reads

export function useCustomerMargins(range: DateRange) {
  return useQuery({
    queryKey: ["margin", "customers", range],
    queryFn: () => customersApi.listCustomerMargins(range),
    // Date-range changes refresh in the background instead of blanking.
    placeholderData: keepPreviousData,
  });
}

export function useCustomerMargin(customerId: string, range: DateRange) {
  return useQuery({
    queryKey: ["margin", "customer", customerId, range],
    queryFn: () => customersApi.getCustomerMargin(customerId, range),
    placeholderData: keepPreviousData,
  });
}

export function useMarginTrend(customerId: string, periods: number) {
  return useQuery({
    queryKey: ["margin", "trend", customerId, periods],
    queryFn: () => customersApi.getMarginTrend(customerId, periods),
    placeholderData: keepPreviousData,
  });
}

export function useRevenueProfile(customerId: string) {
  return useQuery({
    queryKey: ["margin", "revenue", customerId],
    queryFn: () => nullOn404(customersApi.getRevenueProfile(customerId)),
  });
}

export function useRevenueMode(customerId: string) {
  return useQuery({
    queryKey: ["margin", "revenue-mode", customerId],
    queryFn: () => customersApi.getRevenueMode(customerId),
  });
}

/** null = 404 (individual customer, not a business) — callers hide the section. */
export function useBusinessMargin(externalId: string | undefined, range: DateRange) {
  return useQuery({
    queryKey: ["margin", "business", externalId ?? "", range],
    queryFn: () => nullOn404(customersApi.getBusinessMargin(externalId ?? "", range)),
    enabled: Boolean(externalId),
    placeholderData: keepPreviousData,
  });
}

// ---------------------------------------------------------------------------
// Usage reads

export function useUsageAnalytics(customerId: string, range: DateRange) {
  return useQuery({
    queryKey: ["metering", "analytics", "usage", customerId, range],
    queryFn: () => customersApi.getUsageAnalytics(customerId, range),
    placeholderData: keepPreviousData,
  });
}

export function useUsageTimeseries(customerId: string, range: DateRange) {
  return useQuery({
    queryKey: ["metering", "analytics", "timeseries", customerId, range],
    queryFn: () => customersApi.getUsageTimeseries(customerId, range),
    placeholderData: keepPreviousData,
  });
}

export function usePastLimitReport(customerId: string) {
  return useQuery({
    queryKey: ["metering", "past-limit-report", customerId],
    queryFn: () => customersApi.getPastLimitReport(customerId),
  });
}

// ---------------------------------------------------------------------------
// Billing reads

export function useBalance(customerId: string, enabled = true) {
  return useQuery({
    queryKey: ["billing", "balance", customerId],
    queryFn: () => customersApi.getBalance(customerId),
    enabled,
  });
}

export function useTransactionsList(customerId: string) {
  return useCursorList(["billing", "transactions", customerId], (cursor) =>
    customersApi.listTransactions(customerId, cursor),
  );
}

export function useGrantsList(
  customerId: string,
  status: string | undefined,
  enabled = true,
) {
  return useCursorList(
    ["billing", "grants", customerId, { status }],
    (cursor) => customersApi.listGrants(customerId, { status, cursor }),
    { enabled },
  );
}

export function useCustomerBudget(customerId: string) {
  return useQuery({
    queryKey: ["billing", "budget", customerId],
    queryFn: () => customersApi.getCustomerBudget(customerId),
  });
}

export function useBudgetStatus(customerId: string) {
  return useQuery({
    queryKey: ["billing", "budget-status", customerId],
    queryFn: () => customersApi.getBudgetStatus(customerId),
  });
}

export function useBillingProfile(customerId: string, enabled = true) {
  return useQuery({
    queryKey: ["billing", "billing-profile", customerId],
    queryFn: () => customersApi.getBillingProfile(customerId),
    enabled,
  });
}

/** Stripe-push history for this customer's usage invoices (read floor). */
export function useCustomerUsageInvoices(customerId: string) {
  return useCursorList(["billing", "usage-invoices", customerId], (cursor) =>
    customersApi.listCustomerUsageInvoices(customerId, cursor),
  );
}

// ---------------------------------------------------------------------------
// Pricing reads

export function useCustomerMarkup(customerId: string) {
  return useQuery({
    queryKey: ["metering", "customer-markup", customerId],
    queryFn: () => customersApi.getCustomerMarkup(customerId),
  });
}

export function usePriceBooks(enabled = true) {
  return useQuery({
    queryKey: ["metering", "price-books"],
    queryFn: () => customersApi.listPriceBooks(),
    enabled,
  });
}

// ---------------------------------------------------------------------------
// Subscription reads

/** null = 404 (no subscription yet) — callers show the subscribe form. */
export function useSubscription(customerId: string) {
  return useQuery({
    queryKey: ["subscriptions", "customer", customerId],
    queryFn: () => nullOn404(customersApi.getSubscription(customerId)),
  });
}

export function useSubscriptionInvoices(customerId: string, enabled = true) {
  return useCursorList(
    ["subscriptions", "invoices", customerId],
    (cursor) => customersApi.listSubscriptionInvoices(customerId, cursor),
    { enabled },
  );
}

// ---------------------------------------------------------------------------
// Mutations — invalidate every affected namespace prefix (over-invalidate
// rather than miss).

export function useCreateCustomer() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: CreateCustomerRequest) => customersApi.createCustomer(body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["margin"] });
      void queryClient.invalidateQueries({ queryKey: ["platform"] });
    },
  });
}

export function useSaveRevenueProfile(customerId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: RevenueProfileIn) =>
      customersApi.putRevenueProfile(customerId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["margin"] });
    },
  });
}

export function useSaveRevenueMode(customerId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (revenueMode: string) =>
      customersApi.putRevenueMode(customerId, revenueMode),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["margin"] });
    },
  });
}

function useBillingMutation<TArgs, TResult>(
  mutationFn: (args: TArgs) => Promise<TResult>,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["billing"] });
      void queryClient.invalidateQueries({ queryKey: ["margin"] });
      // Money movement can open/clear stop episodes — refresh the metering
      // surfaces (past-limit report, usage lists) too. Over-invalidate
      // rather than miss, mirroring the events feature's refund.
      void queryClient.invalidateQueries({ queryKey: ["metering"] });
    },
  });
}

export function useTopUp(customerId: string) {
  return useBillingMutation((body: CreateTopUpRequest) =>
    customersApi.createTopUp(customerId, body),
  );
}

export function useWithdraw(customerId: string) {
  return useBillingMutation((body: WithdrawRequest) =>
    customersApi.withdraw(customerId, body),
  );
}

/** Takes the EXTERNAL id in body.customer_id. */
export function useCreditWallet() {
  return useBillingMutation((body: CreditRequest) => customersApi.creditWallet(body));
}

/** Takes the EXTERNAL id in body.customer_id. */
export function useDebitWallet() {
  return useBillingMutation((body: DebitRequest) => customersApi.debitWallet(body));
}

/** Read-only verdict — nothing to invalidate; denial arrives as HTTP 200. */
export function usePreCheck(customerId: string) {
  return useMutation({
    mutationFn: () => customersApi.preCheck(customerId),
  });
}

export function useCreateGrant(customerId: string) {
  return useBillingMutation((body: CreateGrantRequest) =>
    customersApi.createGrant(customerId, body),
  );
}

export function useVoidGrant(customerId: string) {
  return useBillingMutation((grantId: string) =>
    customersApi.voidGrant(customerId, grantId),
  );
}

export function useSaveBudget(customerId: string) {
  return useBillingMutation((body: BudgetConfigIn) =>
    customersApi.putCustomerBudget(customerId, body),
  );
}

export function useSaveBillingProfile(customerId: string) {
  return useBillingMutation((body: CustomerBillingProfileIn) =>
    customersApi.putBillingProfile(customerId, body),
  );
}

export function useConfigureAutoTopUp(customerId: string) {
  return useBillingMutation((body: ConfigureAutoTopUpRequest) =>
    customersApi.configureAutoTopUp(customerId, body),
  );
}

// The three pricing mutations write audit records (markup.set /
// markup.deleted / rate_card.assigned) — refresh the audit ledger too.

export function useSaveMarkup(customerId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: TenantMarkupIn) =>
      customersApi.putCustomerMarkup(customerId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["metering"] });
      void queryClient.invalidateQueries({ queryKey: ["margin"] });
      void queryClient.invalidateQueries({ queryKey: ["audit"] });
    },
  });
}

export function useRemoveMarkup(customerId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => customersApi.deleteCustomerMarkup(customerId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["metering"] });
      void queryClient.invalidateQueries({ queryKey: ["margin"] });
      void queryClient.invalidateQueries({ queryKey: ["audit"] });
    },
  });
}

export function useAssignRateCard(customerId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (rateCardId: string) =>
      customersApi.assignRateCard(customerId, rateCardId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["metering"] });
      void queryClient.invalidateQueries({ queryKey: ["margin"] });
      void queryClient.invalidateQueries({ queryKey: ["audit"] });
    },
  });
}

function useSubscriptionMutation<TArgs, TResult>(
  mutationFn: (args: TArgs) => Promise<TResult>,
) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["subscriptions"] });
      void queryClient.invalidateQueries({ queryKey: ["platform"] });
      void queryClient.invalidateQueries({ queryKey: ["margin"] });
    },
  });
}

export function useSubscribe(externalId: string) {
  return useSubscriptionMutation((body: SubscribeIn) =>
    customersApi.subscribeCustomer(externalId, body),
  );
}

export function useCancelSubscription(externalId: string) {
  return useSubscriptionMutation((atPeriodEnd: boolean) =>
    customersApi.cancelSubscription(externalId, atPeriodEnd),
  );
}

export function usePauseSubscription(externalId: string) {
  return useSubscriptionMutation((_: void) =>
    customersApi.pauseSubscription(externalId),
  );
}

export function useResumeSubscription(externalId: string) {
  return useSubscriptionMutation((_: void) =>
    customersApi.resumeSubscription(externalId),
  );
}

export function useSetSeats(externalId: string) {
  return useSubscriptionMutation((seats: number) =>
    customersApi.setSeats(externalId, seats),
  );
}
