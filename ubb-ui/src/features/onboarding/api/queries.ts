import { useMutation } from "@tanstack/react-query";
import { toastOnError } from "@/lib/mutations";
import { onboardingApi } from "./provider";
import type { ValidateKeyRequest, MatchCustomersRequest, ActivateRequest } from "./types";

export function useValidateStripeKey() {
  return useMutation({
    mutationFn: (req: ValidateKeyRequest) => onboardingApi.validateStripeKey(req),
    onError: toastOnError("Couldn't validate Stripe key"),
  });
}

export function useMatchCustomers() {
  return useMutation({
    mutationFn: (req: MatchCustomersRequest) => onboardingApi.matchCustomers(req),
    onError: toastOnError("Couldn't match customers"),
  });
}

export function useActivateOnboarding() {
  return useMutation({
    mutationFn: (req: ActivateRequest) => onboardingApi.activateOnboarding(req),
    onError: toastOnError("Couldn't activate onboarding"),
  });
}
