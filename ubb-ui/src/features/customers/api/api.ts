// src/features/customers/api/api.ts
import type { CustomerMappingData } from "./types";
import { platformApi } from "@/api/client";

export async function getCustomerMapping(): Promise<CustomerMappingData> {
  const { data } = await platformApi.GET("/customers/mapping", {});
  return data as CustomerMappingData;
}

export async function updateMapping(
  customerId: string,
  sdkIdentifier: string,
): Promise<void> {
  await platformApi.PUT("/customers/mapping/{customerId}", {
    params: { path: { customerId } },
    body: { sdkIdentifier },
  });
}

export async function assignOrphan(
  orphanId: string,
  stripeCustomerId: string,
): Promise<void> {
  await platformApi.POST("/customers/orphans/{orphanId}/assign", {
    params: { path: { orphanId } },
    body: { stripeCustomerId },
  });
}

export async function dismissOrphans(): Promise<void> {
  await platformApi.DELETE("/customers/orphans", {});
}

export async function triggerSync(): Promise<void> {
  await platformApi.POST("/customers/sync", {});
}
