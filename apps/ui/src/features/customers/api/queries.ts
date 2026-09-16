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
import {
  toCustomerRows,
  toOneCustomer,
  toTimeseriesPoints,
  toTrendPoints,
} from "./types";
import type {
  CustomerSpendPoolIn,
  ConfigureAutoTopUpRequest,
  CreateCustomerRequest,
  CreateGrantRequest,
  CreateTopUpRequest,
  CreditRequest,
  CustomerBillingProfileIn,
  DebitRequest,
  SubscribeIn,
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

export function useCustomerIdentity(customerId: string) {
  return useQuery({
    queryKey: ["platform", "customers", customerId] as const,
    queryFn: () => customersApi.getCustomerIdentity(customerId),
  });
}

export function useCustomerMargins(range: DateRange) {
  return useQuery({
    queryKey: ["margin", "customers", range],
    queryFn: () => customersApi.listCustomerMargins(range),
    select: toCustomerRows,
    // Date-range changes refresh in the background instead of blanking.
    placeholderData: keepPreviousData,
  });
}

export function useCustomerMargin(customerId: string, range: DateRange) {
  return useQuery({
    queryKey: ["margin", "customer", customerId, range],
    queryFn: () => customersApi.getCustomerMargin(customerId, range),
    select: toOneCustomer,
    placeholderData: keepPreviousData,
  });
}

export function useMarginTrend(customerId: string, periods: number) {
  return useQuery({
    queryKey: ["margin", "trend", customerId, periods],
    queryFn: () => customersApi.getMarginTrend(customerId, periods),
    select: toTrendPoints,
    placeholderData: keepPreviousData,
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

// ⚠ THE SAME KEY AS `useCustomerMargin`, DELIBERATELY. The Usage tab wants
// one customer's figures for a window, which is exactly what the Overview tab
// wants, so sharing the key makes the two tabs share one fetch and one cached
// answer instead of racing two identical requests to the same route. The hooks
// stay separate because each tab reads the answer for its own reason and a
// `select` is per-caller; what they must not have is two ANSWERS.
export function useUsageAnalytics(customerId: string, range: DateRange) {
  return useQuery({
    queryKey: ["margin", "customer", customerId, range],
    queryFn: () => customersApi.getCustomerMargin(customerId, range),
    select: toOneCustomer,
    placeholderData: keepPreviousData,
  });
}

export function useUsageTimeseries(customerId: string, range: DateRange) {
  return useQuery({
    queryKey: ["metering", "analytics", "timeseries", customerId, range],
    queryFn: () => customersApi.getUsageTimeseries(customerId, range),
    select: toTimeseriesPoints,
    placeholderData: keepPreviousData,
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

export function useCustomerSpendPool(customerId: string) {
  return useQuery({
    queryKey: ["billing", "customer-spend-pool", customerId],
    queryFn: () => customersApi.getCustomerSpendPool(customerId),
  });
}

export function useCustomerSpendPoolStatus(customerId: string) {
  return useQuery({
    queryKey: ["billing", "customer-spend-pool-status", customerId],
    queryFn: () => customersApi.getCustomerSpendPoolStatus(customerId),
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
//
// ⚠ THERE ARE NONE, AND THAT IS NOW A BOUNDARY RATHER THAN A GAP. The two
// hooks that were here went with the records and routes behind them (#368,
// #369). A customer's price resolves from a rule in a pricing book, and the
// hooks that read and write one live in `features/pricing/api/queries.ts`
// (#372) — where the rest of that entity's cache keys and invalidation already
// are. Two features holding query keys for one entity is how a mutation comes
// to invalidate half of what it moved.

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

// THE REVENUE-SWITCH READ AND WRITE WERE HERE AND ARE GONE (#497, slice 7
// section 9), with the route pair behind them. The setting they moved decided
// whether a customer's billed usage counted as revenue at all, which is not a
// question a customer-level setting was ever entitled to answer: the price
// status on each posting answers it, one posting at a time.

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
      // surfaces (the usage lists) and Stops and breaches, which the Usage
      // tab hosts, too. Over-invalidate rather than miss, mirroring the
      // events feature's refund.
      void queryClient.invalidateQueries({ queryKey: ["metering"] });
      void queryClient.invalidateQueries({ queryKey: ["spend-controls"] });
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

/**
 * The affordability question — a read, asked on demand. A mutation hook
 * rather than a query because the dialog asks it when a person presses the
 * button and shows that answer, never a cached one; nothing to invalidate,
 * and a denial arrives as HTTP 200.
 */
export function useAffordability(customerId: string) {
  return useMutation({
    mutationFn: () => customersApi.affordability(customerId),
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

export function useSaveCustomerSpendPool(customerId: string) {
  return useBillingMutation((body: CustomerSpendPoolIn) =>
    customersApi.putCustomerSpendPool(customerId, body),
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

// ⚠ NO PRICING MUTATIONS HERE EITHER (#368, #369). The three that were — save
// a markup override, remove one, assign a book — all wrote audit records, which
// is why they invalidated the "audit" namespace as well as "metering" and
// "margin". Their records and routes are deleted.


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
