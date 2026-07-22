import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { toastOnError } from "@/lib/mutations";
import { useCursorList } from "@/lib/use-cursor-list";
import * as api from "./api";
import type { PlanIn, PlanUpdateIn } from "./types";

const SUBS_KEY = ["subscriptions"] as const;

export function useSyncSubscriptions() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: () => api.syncSubscriptions(),
    onSuccess: (res) => {
      qc.invalidateQueries({ queryKey: SUBS_KEY });
      toast.success(
        `Sync complete — ${res.synced} synced, ${res.skipped} skipped, ${res.errors} errors`,
      );
    },
    onError: toastOnError("Couldn't sync subscriptions"),
  });
}

export function useCustomerSubscription(customerId: string) {
  return useQuery({
    queryKey: [...SUBS_KEY, "customer", customerId],
    queryFn: () => api.getCustomerSubscription(customerId),
    enabled: !!customerId,
    retry: false,
  });
}

export function useCustomerInvoices(customerId: string) {
  return useCursorList({
    queryKeyBase: [...SUBS_KEY, "invoices", customerId],
    fetchPage: (cursor) => api.listCustomerInvoices(customerId, { cursor, limit: 50 }),
    enabled: !!customerId,
  });
}

export function useCreatePlan() {
  return useMutation({
    mutationFn: (body: PlanIn) => api.createPlan(body),
    onSuccess: (plan) => toast.success(`Plan "${plan.name}" created`),
    onError: toastOnError("Couldn't create plan"),
  });
}

export function useUpdatePlan() {
  return useMutation({
    mutationFn: ({ key, body }: { key: string; body: PlanUpdateIn }) =>
      api.updatePlan(key, body),
    onSuccess: () => toast.success("Plan updated"),
    onError: toastOnError("Couldn't update plan"),
  });
}
