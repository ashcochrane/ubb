import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { toastOnError } from "@/lib/mutations";
import { useCursorList } from "@/lib/use-cursor-list";
import * as api from "./api";
import type {
  AttributeReferral,
  ProgramCreate,
  ProgramUpdate,
  RegisterReferrer,
} from "./types";

const ROOT = ["referrals"] as const;
const PROGRAM_KEY = [...ROOT, "program"] as const;
const REFERRERS_KEY = [...ROOT, "referrers"] as const;
const ANALYTICS_KEY = [...ROOT, "analytics"] as const;

// --- Program ---------------------------------------------------------------

export function useProgram() {
  return useQuery({
    queryKey: PROGRAM_KEY,
    queryFn: api.getProgram,
    // No program configured yet surfaces as an error; don't hammer the endpoint.
    retry: false,
  });
}

export function useCreateProgram() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ProgramCreate) => api.createProgram(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PROGRAM_KEY });
      toast.success("Referral program created");
    },
    onError: toastOnError("Couldn't create referral program"),
  });
}

export function useUpdateProgram() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: ProgramUpdate) => api.updateProgram(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PROGRAM_KEY });
      toast.success("Referral program updated");
    },
    onError: toastOnError("Couldn't update referral program"),
  });
}

export function useDeactivateProgram() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.deactivateProgram(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PROGRAM_KEY });
      toast.success("Referral program deactivated");
    },
    onError: toastOnError("Couldn't deactivate program"),
  });
}

export function useReactivateProgram() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.reactivateProgram(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: PROGRAM_KEY });
      toast.success("Referral program reactivated");
    },
    onError: toastOnError("Couldn't reactivate program"),
  });
}

// --- Referrers -------------------------------------------------------------

export function useReferrers() {
  return useCursorList({
    queryKeyBase: REFERRERS_KEY,
    fetchPage: (cursor) => api.listReferrers({ cursor, limit: 50 }),
  });
}

export function useReferrer(customerId: string) {
  return useQuery({
    queryKey: [...REFERRERS_KEY, "one", customerId],
    queryFn: () => api.getReferrer(customerId),
    enabled: !!customerId,
    retry: false,
  });
}

export function useReferrerEarnings(customerId: string) {
  return useQuery({
    queryKey: [...REFERRERS_KEY, "earnings", customerId],
    queryFn: () => api.getReferrerEarnings(customerId),
    enabled: !!customerId,
  });
}

export function useReferrerReferrals(customerId: string) {
  return useCursorList({
    queryKeyBase: [...REFERRERS_KEY, "referrals", customerId],
    fetchPage: (cursor) =>
      api.listReferrerReferrals(customerId, { cursor, limit: 50 }),
    enabled: !!customerId,
  });
}

export function useRegisterReferrer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: RegisterReferrer) => api.registerReferrer(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: REFERRERS_KEY });
      toast.success("Referrer registered");
    },
    onError: toastOnError("Couldn't register referrer"),
  });
}

// --- Attribution & referrals ----------------------------------------------

export function useAttributeReferral() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: AttributeReferral) => api.attributeReferral(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: REFERRERS_KEY });
      qc.invalidateQueries({ queryKey: ANALYTICS_KEY });
      toast.success("Referral attributed");
    },
    onError: toastOnError("Couldn't attribute referral"),
  });
}

export function useRevokeReferral(customerId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (referralId: string) => api.revokeReferral(referralId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: REFERRERS_KEY });
      qc.invalidateQueries({
        queryKey: [...REFERRERS_KEY, "earnings", customerId],
      });
      qc.invalidateQueries({ queryKey: ANALYTICS_KEY });
      toast.success("Referral revoked");
    },
    onError: toastOnError("Couldn't revoke referral"),
  });
}

export function useReferralLedger(referralId: string, enabled = true) {
  return useCursorList({
    queryKeyBase: [...ROOT, "ledger", referralId],
    fetchPage: (cursor) =>
      api.getReferralLedger(referralId, { cursor, limit: 50 }),
    enabled: enabled && !!referralId,
  });
}

// --- Analytics & payouts ---------------------------------------------------

export function useAnalyticsSummary() {
  return useQuery({
    queryKey: [...ANALYTICS_KEY, "summary"],
    queryFn: api.getAnalyticsSummary,
  });
}

export function useAnalyticsEarnings(range: {
  period_start?: string;
  period_end?: string;
}) {
  return useQuery({
    queryKey: [...ANALYTICS_KEY, "earnings", range],
    queryFn: () => api.getAnalyticsEarnings(range),
  });
}

export function usePayoutExport() {
  return useQuery({
    queryKey: [...ROOT, "payouts", "export"],
    queryFn: api.getPayoutExport,
  });
}
