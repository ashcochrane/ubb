import type { CreateTenantRequest, CreateTenantResponse } from "./types";
import { platformApi } from "@/api/client";

export async function createTenant(
  req: CreateTenantRequest
): Promise<CreateTenantResponse> {
  const { data, error } = await platformApi.POST("/tenant", { body: req });
  if (error) throw new Error("Failed to create tenant");
  return data as CreateTenantResponse;
}

export async function completeOnboarding(): Promise<void> {
  const { error } = await platformApi.PATCH("/tenant", {
    body: { completeOnboarding: true },
  });
  if (error) throw new Error("Failed to complete onboarding");
}
