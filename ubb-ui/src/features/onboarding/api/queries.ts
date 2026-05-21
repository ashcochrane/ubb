import { useMutation, useQueryClient } from "@tanstack/react-query";
import { onboardingApi } from "./provider";
import type { CreateTenantRequest, CreateTenantResponse } from "./types";

export function useCreateTenant() {
  const qc = useQueryClient();
  return useMutation<CreateTenantResponse, Error, CreateTenantRequest>({
    mutationFn: (req) => onboardingApi.createTenant(req),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["me"] });
    },
  });
}

export function useCompleteOnboarding() {
  const qc = useQueryClient();
  return useMutation<void, Error, void>({
    mutationFn: () => onboardingApi.completeOnboarding(),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["me"] });
    },
  });
}
