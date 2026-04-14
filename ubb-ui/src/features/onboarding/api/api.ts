import type {
  StripeValidationResult,
  StripeSyncPreview,
  MatchResult,
  MatchCustomersRequest,
  ValidateKeyRequest,
  ActivateRequest,
} from "./types";
import { tenantApi } from "@/api/client";

export async function validateStripeKey(req: ValidateKeyRequest): Promise<{
  validation: StripeValidationResult;
  preview: StripeSyncPreview;
}> {
  const { data } = await tenantApi.POST("/onboarding/validate-stripe-key", { body: req });
  return data as { validation: StripeValidationResult; preview: StripeSyncPreview };
}

export async function matchCustomers(req: MatchCustomersRequest): Promise<MatchResult> {
  const { data } = await tenantApi.POST("/onboarding/match-customers", { body: req });
  return data as MatchResult;
}

export async function activateOnboarding(req: ActivateRequest): Promise<{ success: boolean }> {
  const { data } = await tenantApi.POST("/onboarding/activate", { body: req });
  return data as { success: boolean };
}
