// src/features/customers/api/types.ts

// Data semantics use "unmapped"; display label is "New" (teal pill)
export type CustomerStatus = "active" | "idle" | "unmapped";

export type CustomerFilterKey = "all" | "active" | "idle" | "unmapped";

export interface CustomerMapping {
  id: string;
  stripeCustomerId: string;
  name: string;
  email: string;
  sdkIdentifier: string | null;
  revenue30d: number; // micros
  events30d: number;
  lastEventAt: string | null; // ISO timestamp
  status: CustomerStatus;
}

export interface OrphanedIdentifier {
  id: string;
  sdkIdentifier: string;
  firstSeenAt: string; // ISO timestamp
  eventCount: number;
  unattributedCost: number; // micros
}

export interface SyncStatus {
  connected: boolean;
  lastSyncAt: string | null; // ISO timestamp
  syncing: boolean;
}

export interface CustomerMappingStats {
  totalCustomers: number;
  mapped: number;
  unmapped: number;
  orphanedEvents: number;
  orphanedIdentifiers: number;
  newCustomersSinceLastSync: number;
}

export interface CustomerMappingData {
  syncStatus: SyncStatus;
  stats: CustomerMappingStats;
  customers: CustomerMapping[];
  orphanedIdentifiers: OrphanedIdentifier[];
}
