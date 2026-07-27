// TanStack Query hooks for the subscriptions surface. All query keys and
// invalidation live here. First key segment = backend namespace.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { toastOnError } from "@/lib/mutations";

import { subscriptionsFeatureApi } from "./provider";
import type { PlanIn, PlanUpdateIn } from "./types";

export const connectStatusQueryKey = ["connect", "status"] as const;

export function useConnectStatus() {
  return useQuery({
    queryKey: connectStatusQueryKey,
    queryFn: () => subscriptionsFeatureApi.getConnectStatus(),
  });
}

/** POST /platform/plans. Errors surface inline in the form (409 duplicate key). */
export function useCreatePlan() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: PlanIn) => subscriptionsFeatureApi.createPlan(input),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["platform"] });
      void queryClient.invalidateQueries({ queryKey: ["subscriptions"] });
    },
  });
}

/** PATCH /platform/plans/{key}. Errors surface inline in the form (404 unknown key). */
export function useUpdatePlan() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ key, input }: { key: string; input: PlanUpdateIn }) =>
      subscriptionsFeatureApi.updatePlan(key, input),
    onSuccess: () => {
      // migrate_existing can repoint live subscriptions, which feeds margin.
      void queryClient.invalidateQueries({ queryKey: ["platform"] });
      void queryClient.invalidateQueries({ queryKey: ["subscriptions"] });
      void queryClient.invalidateQueries({ queryKey: ["margin"] });
    },
  });
}

/** POST /subscriptions/sync — synchronous mirror refresh from Stripe. */
export function useTriggerSync() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => subscriptionsFeatureApi.triggerSync(),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["subscriptions"] });
      void queryClient.invalidateQueries({ queryKey: ["margin"] });
    },
    onError: toastOnError("Couldn't sync with Stripe"),
  });
}
