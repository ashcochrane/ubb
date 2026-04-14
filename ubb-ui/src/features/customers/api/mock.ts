// src/features/customers/api/mock.ts
import type { CustomerMappingData } from "./types";
import { mockCustomerMappingData } from "./mock-data";
import { mockDelay } from "@/lib/api-provider";

// Session-local mutable copy so mock mutations persist across calls
const sessionData: CustomerMappingData = structuredClone(mockCustomerMappingData);

export async function getCustomerMapping(): Promise<CustomerMappingData> {
  await mockDelay();
  return structuredClone(sessionData);
}

export async function updateMapping(
  customerId: string,
  sdkIdentifier: string,
): Promise<void> {
  await mockDelay();
  const customer = sessionData.customers.find((c) => c.id === customerId);
  if (!customer) throw new Error(`Customer ${customerId} not found`);
  const wasUnmapped = !customer.sdkIdentifier;
  customer.sdkIdentifier = sdkIdentifier;
  if (wasUnmapped) {
    customer.status = "idle";
    customer.events30d = 0;
    sessionData.stats.mapped += 1;
    sessionData.stats.unmapped -= 1;
  }
}

export async function assignOrphan(
  orphanId: string,
  stripeCustomerId: string,
): Promise<void> {
  await mockDelay();
  const idx = sessionData.orphanedIdentifiers.findIndex(
    (o) => o.id === orphanId,
  );
  if (idx === -1) throw new Error(`Orphan ${orphanId} not found`);
  const orphan = sessionData.orphanedIdentifiers[idx]!;
  sessionData.stats.orphanedEvents -= orphan.eventCount;
  sessionData.stats.orphanedIdentifiers -= 1;
  sessionData.orphanedIdentifiers.splice(idx, 1);
  // Create mapping: associate orphan's SDK identifier with the Stripe customer
  const customer = sessionData.customers.find(
    (c) => c.stripeCustomerId === stripeCustomerId,
  );
  if (customer && !customer.sdkIdentifier) {
    customer.sdkIdentifier = orphan.sdkIdentifier;
    customer.status = "idle";
    sessionData.stats.mapped += 1;
    sessionData.stats.unmapped -= 1;
  }
}

export async function dismissOrphans(): Promise<void> {
  await mockDelay();
  sessionData.stats.orphanedEvents = 0;
  sessionData.stats.orphanedIdentifiers = 0;
  sessionData.orphanedIdentifiers = [];
}

export async function triggerSync(): Promise<void> {
  await mockDelay(1200);
  sessionData.syncStatus.lastSyncAt = new Date().toISOString();
}
