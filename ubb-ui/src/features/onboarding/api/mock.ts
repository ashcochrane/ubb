import type { CreateTenantRequest, CreateTenantResponse } from "./types";
import type { MeTenant } from "@/features/auth/api/types";
import { mockDelay } from "@/lib/api-provider";

export async function createTenant(
  req: CreateTenantRequest
): Promise<CreateTenantResponse> {
  await mockDelay();
  const tenant: MeTenant = {
    id: "mock-tenant-" + Date.now(),
    name: req.name,
    products: ["metering"],
    pricingCardsCount: 0,
    usageEventsCount: 0,
  };
  return {
    tenant,
    apiKey: "ubb_test_mockkey_" + Math.random().toString(36).slice(2, 10),
  };
}

export async function completeOnboarding(): Promise<void> {
  await mockDelay();
}
