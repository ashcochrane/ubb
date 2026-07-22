import type { Me } from "./types";
import { mockDelay } from "@/lib/api-provider";

export async function getMe(): Promise<Me> {
  await mockDelay();
  return {
    tenantUser: {
      id: "mock-tu-1",
      email: "mock@example.com",
      role: "owner",
    },
    tenant: {
      id: "mock-tenant-1",
      name: "Mock Workspace",
      products: ["metering"],
      pricingCardsCount: 3,
      usageEventsCount: 42,
    },
    onboardingCompleted: true,
  };
}
