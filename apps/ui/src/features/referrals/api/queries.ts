// TanStack Query hooks for the referrals surface. ALL query keys and
// invalidation live here (first key segment = backend namespace). Mutations
// over-invalidate the whole ['referrals'] prefix — program, referrers,
// referrals, and analytics all shift together.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useCursorList } from "@/api/pagination";
import { isNotFound } from "@/api/problem";
import { toastOnError } from "@/lib/mutations";

import { referralsApi } from "./provider";
import type {
  AttributeRequest,
  EarningsPeriodParams,
  ProgramCreateRequest,
  ProgramOut,
  ProgramUpdateRequest,
} from "./types";

export const referralKeys = {
  all: ["referrals"] as const,
  program: ["referrals", "program"] as const,
  analyticsSummary: ["referrals", "analytics", "summary"] as const,
  analyticsEarnings: (params: EarningsPeriodParams) =>
    ["referrals", "analytics", "earnings", params] as const,
  referrers: ["referrals", "referrers"] as const,
  referrer: (customerId: string) => ["referrals", "referrers", customerId] as const,
  referrerEarnings: (customerId: string) =>
    ["referrals", "referrers", customerId, "earnings"] as const,
  referrerReferrals: (customerId: string) =>
    ["referrals", "referrers", customerId, "referrals"] as const,
  referralLedger: (referralId: string) =>
    ["referrals", "referrals", referralId, "ledger"] as const,
  payoutExport: ["referrals", "payouts", "export"] as const,
  marginCustomerPicker: ["margin", "customers", "referral-picker"] as const,
};

// --- Reads -------------------------------------------------------------------

/**
 * The tenant's referral program, or `null` when none exists yet (the GET
 * answers a runtime 404 that the schema doesn't document — we treat it as
 * the empty state, not an error).
 */
export function useProgram() {
  return useQuery<ProgramOut | null>({
    queryKey: referralKeys.program,
    queryFn: async () => {
      try {
        return await referralsApi.getProgram();
      } catch (error) {
        if (isNotFound(error)) return null;
        throw error;
      }
    },
  });
}

export function useAnalyticsSummary() {
  return useQuery({
    queryKey: referralKeys.analyticsSummary,
    queryFn: () => referralsApi.getAnalyticsSummary(),
  });
}

export function useAnalyticsEarnings(params: EarningsPeriodParams) {
  return useQuery({
    queryKey: referralKeys.analyticsEarnings(params),
    queryFn: () => referralsApi.getAnalyticsEarnings(params),
  });
}

export function useReferrers() {
  return useCursorList(referralKeys.referrers, (cursor) => referralsApi.listReferrers(cursor));
}

export function useReferrer(customerId: string) {
  return useQuery({
    queryKey: referralKeys.referrer(customerId),
    queryFn: () => referralsApi.getReferrer(customerId),
  });
}

export function useReferrerEarnings(customerId: string) {
  return useQuery({
    queryKey: referralKeys.referrerEarnings(customerId),
    queryFn: () => referralsApi.getReferrerEarnings(customerId),
  });
}

export function useReferrerReferrals(customerId: string) {
  return useCursorList(referralKeys.referrerReferrals(customerId), (cursor) =>
    referralsApi.listReferrerReferrals(customerId, cursor),
  );
}

export function useReferralLedger(referralId: string, enabled: boolean) {
  return useCursorList(
    referralKeys.referralLedger(referralId),
    (cursor) => referralsApi.getReferralLedger(referralId, cursor),
    { enabled },
  );
}

/** On-demand payout snapshot — only fetched once the user asks for it. */
export function usePayoutExport(enabled: boolean) {
  return useQuery({
    queryKey: referralKeys.payoutExport,
    queryFn: () => referralsApi.getPayoutExport(),
    enabled,
    staleTime: 0,
  });
}

/**
 * Customer feed for the register-referrer picker. Margin may be unavailable
 * (product off / role) — never retried, and callers fall back to the free
 * UUID input on failure.
 */
export function useMarginCustomerPicker(enabled: boolean) {
  return useQuery({
    queryKey: referralKeys.marginCustomerPicker,
    queryFn: () => referralsApi.listMarginCustomers(),
    enabled,
    staleTime: 60_000,
    retry: 0,
  });
}

// --- Mutations ---------------------------------------------------------------

function useInvalidateReferrals() {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: referralKeys.all });
}

/** Program config mutations also write audit records — refresh that ledger too. */
function useInvalidateProgramOps() {
  const queryClient = useQueryClient();
  return () => {
    void queryClient.invalidateQueries({ queryKey: referralKeys.all });
    void queryClient.invalidateQueries({ queryKey: ["audit"] });
  };
}

export function useCreateProgram() {
  const invalidate = useInvalidateProgramOps();
  return useMutation({
    mutationFn: (body: ProgramCreateRequest) => referralsApi.createProgram(body),
    onSuccess: invalidate,
  });
}

export function useUpdateProgram() {
  const invalidate = useInvalidateProgramOps();
  return useMutation({
    mutationFn: (body: ProgramUpdateRequest) => referralsApi.updateProgram(body),
    onSuccess: invalidate,
  });
}

export function useDeactivateProgram() {
  const invalidate = useInvalidateProgramOps();
  return useMutation({
    mutationFn: () => referralsApi.deactivateProgram(),
    onSuccess: invalidate,
    onError: toastOnError("Couldn't deactivate the program"),
  });
}

export function useReactivateProgram() {
  const invalidate = useInvalidateProgramOps();
  return useMutation({
    mutationFn: () => referralsApi.reactivateProgram(),
    onSuccess: invalidate,
    onError: toastOnError("Couldn't reactivate the program"),
  });
}

export function useRegisterReferrer() {
  const invalidate = useInvalidateReferrals();
  return useMutation({
    mutationFn: (customerId: string) => referralsApi.registerReferrer(customerId),
    onSuccess: invalidate,
  });
}

export function useAttributeReferral() {
  const invalidate = useInvalidateReferrals();
  return useMutation({
    mutationFn: (body: AttributeRequest) => referralsApi.attributeReferral(body),
    onSuccess: invalidate,
  });
}

export function useRevokeReferral() {
  const invalidate = useInvalidateReferrals();
  return useMutation({
    mutationFn: (referralId: string) => referralsApi.revokeReferral(referralId),
    onSuccess: invalidate,
    onError: toastOnError("Couldn't revoke the referral"),
  });
}
