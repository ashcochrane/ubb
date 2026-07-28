// TanStack Query hooks for the plans surface. All query keys and
// invalidation live here. First key segment = backend namespace.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { archivePlan, createPlan, listPlans, updatePlan } from "./api";
import type { PlanInput, PlanUpdateInput } from "./types";

const PLANS_KEY = ["plans"] as const;

export function usePlans() {
  return useQuery({ queryKey: PLANS_KEY, queryFn: listPlans });
}

export function useCreatePlan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (input: PlanInput) => createPlan(input),
    onSuccess: () => qc.invalidateQueries({ queryKey: PLANS_KEY }),
  });
}

export function useUpdatePlan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ key, input }: { key: string; input: PlanUpdateInput }) =>
      updatePlan(key, input),
    onSuccess: () => qc.invalidateQueries({ queryKey: PLANS_KEY }),
  });
}

export function useArchivePlan() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (key: string) => archivePlan(key),
    onSuccess: () => qc.invalidateQueries({ queryKey: PLANS_KEY }),
  });
}
