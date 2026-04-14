// src/features/customers/api/mock-data.ts
import type {
  CustomerMapping,
  CustomerMappingData,
  OrphanedIdentifier,
} from "./types";

/** Compute an ISO timestamp N minutes before now. */
function minutesAgo(mins: number): string {
  return new Date(Date.now() - mins * 60_000).toISOString();
}

const customers: CustomerMapping[] = [
  { id: "1", stripeCustomerId: "cus_R4kB9xPm2nQ", name: "Acme Corp", email: "admin@acmecorp.com", sdkIdentifier: "cus_R4kB9xPm2nQ", revenue30d: 2_400_000_000, events30d: 14_219, lastEventAt: minutesAgo(2), status: "active" },
  { id: "2", stripeCustomerId: "cus_Q7mN3vHj8wL", name: "BrightPath Ltd", email: "team@brightpath.io", sdkIdentifier: "cus_Q7mN3vHj8wL", revenue30d: 1_800_000_000, events30d: 11_402, lastEventAt: minutesAgo(5), status: "active" },
  { id: "3", stripeCustomerId: "cus_S2pK5tRn7xY", name: "NovaTech Inc", email: "ops@novatech.co", sdkIdentifier: "cus_S2pK5tRn7xY", revenue30d: 950_000_000, events30d: 6_841, lastEventAt: minutesAgo(12), status: "active" },
  { id: "4", stripeCustomerId: "cus_U6nR2wKm9xQ", name: "Helios Digital", email: "hello@helios.dev", sdkIdentifier: "cus_U6nR2wKm9xQ", revenue30d: 720_000_000, events30d: 9_403, lastEventAt: minutesAgo(8), status: "active" },
  { id: "5", stripeCustomerId: "cus_T9wM1kJp4qB", name: "Zenith Labs", email: "info@zenithlabs.com", sdkIdentifier: "cus_T9wM1kJp4qB", revenue30d: 680_000_000, events30d: 5_120, lastEventAt: minutesAgo(60), status: "active" },
  { id: "6", stripeCustomerId: "cus_V3bP8sHn5mJ", name: "ClearView Analytics", email: "support@clearview.ai", sdkIdentifier: "cus_V3bP8sHn5mJ", revenue30d: 150_000_000, events30d: 8_210, lastEventAt: minutesAgo(22), status: "active" },
  { id: "7", stripeCustomerId: "cus_W1cT4rFk7pN", name: "Eko Systems", email: "dev@ekosystems.io", sdkIdentifier: "cus_W1cT4rFk7pN", revenue30d: 90_000_000, events30d: 7_891, lastEventAt: minutesAgo(3), status: "active" },
  { id: "8", stripeCustomerId: "cus_X5rW8nKp3mQ", name: "Pinnacle AI", email: "cto@pinnacle.ai", sdkIdentifier: "cus_X5rW8nKp3mQ", revenue30d: 340_000_000, events30d: 2_104, lastEventAt: minutesAgo(45), status: "active" },
  { id: "9", stripeCustomerId: "cus_Y2dF6hTn8qR", name: "Meridian Group", email: "ops@meridian.co", sdkIdentifier: "cus_Y2dF6hTn8qR", revenue30d: 480_000_000, events30d: 3_812, lastEventAt: minutesAgo(60), status: "active" },
  { id: "10", stripeCustomerId: "cus_Z3eG7jUo9sS", name: "Atlas Robotics", email: "api@atlas-robotics.com", sdkIdentifier: "cus_Z3eG7jUo9sS", revenue30d: 320_000_000, events30d: 2_310, lastEventAt: minutesAgo(120), status: "active" },
  { id: "11", stripeCustomerId: "cus_A4fH8kVp0tT", name: "Quantum Logic", email: "dev@quantumlogic.io", sdkIdentifier: "cus_A4fH8kVp0tT", revenue30d: 275_000_000, events30d: 1_891, lastEventAt: minutesAgo(180), status: "active" },
  { id: "12", stripeCustomerId: "cus_B5gI9lWq1uU", name: "BlueSky Data", email: "team@blueskydata.com", sdkIdentifier: "cus_B5gI9lWq1uU", revenue30d: 210_000_000, events30d: 1_402, lastEventAt: minutesAgo(240), status: "active" },
  { id: "13", stripeCustomerId: "cus_C6hJ0mXr2vV", name: "Vertex Labs", email: "eng@vertex.dev", sdkIdentifier: "cus_C6hJ0mXr2vV", revenue30d: 190_000_000, events30d: 980, lastEventAt: minutesAgo(360), status: "active" },
  { id: "14", stripeCustomerId: "cus_D7iK1nYs3wW", name: "Forge AI", email: "hello@forge-ai.com", sdkIdentifier: "cus_D7iK1nYs3wW", revenue30d: 165_000_000, events30d: 820, lastEventAt: minutesAgo(300), status: "active" },
  { id: "15", stripeCustomerId: "cus_E8jL2oZt4xX", name: "Echo Systems", email: "api@echo-sys.io", sdkIdentifier: "cus_E8jL2oZt4xX", revenue30d: 140_000_000, events30d: 650, lastEventAt: minutesAgo(480), status: "active" },
  { id: "16", stripeCustomerId: "cus_F9kM3pAu5yY", name: "Ridgeline", email: "tech@ridgeline.co", sdkIdentifier: "cus_F9kM3pAu5yY", revenue30d: 120_000_000, events30d: 410, lastEventAt: minutesAgo(720), status: "active" },
  { id: "17", stripeCustomerId: "cus_G0lN4qBv6zZ", name: "Prism Health", email: "dev@prismhealth.com", sdkIdentifier: "cus_G0lN4qBv6zZ", revenue30d: 95_000_000, events30d: 220, lastEventAt: minutesAgo(1440), status: "active" },
  { id: "18", stripeCustomerId: "cus_H1mO5rCw7aA", name: "Aether Inc", email: "eng@aether.inc", sdkIdentifier: "cus_H1mO5rCw7aA", revenue30d: 60_000_000, events30d: 102, lastEventAt: minutesAgo(2880), status: "active" },
  { id: "19", stripeCustomerId: "cus_I2nP6sDx8bB", name: "Nomad Digital", email: "api@nomad.digital", sdkIdentifier: "cus_I2nP6sDx8bB", revenue30d: 45_000_000, events30d: 0, lastEventAt: null, status: "idle" },
  { id: "20", stripeCustomerId: "cus_J3oQ7tEy9cC", name: "Strata Corp", email: "tech@strata.io", sdkIdentifier: "cus_J3oQ7tEy9cC", revenue30d: 30_000_000, events30d: 0, lastEventAt: null, status: "idle" },
  { id: "21", stripeCustomerId: "cus_K4pR8uFz0dD", name: "Cobalt Labs", email: "dev@cobalt-labs.com", sdkIdentifier: "cus_K4pR8uFz0dD", revenue30d: 15_000_000, events30d: 0, lastEventAt: null, status: "idle" },
  { id: "22", stripeCustomerId: "cus_L5qS9vGa1eE", name: "Terraform Solutions", email: "hello@terraform-sol.com", sdkIdentifier: null, revenue30d: 380_000_000, events30d: 0, lastEventAt: null, status: "unmapped" },
  { id: "23", stripeCustomerId: "cus_M6rT0wHb2fF", name: "Orbit Analytics", email: "team@orbit-analytics.io", sdkIdentifier: null, revenue30d: 125_000_000, events30d: 0, lastEventAt: null, status: "unmapped" },
];

const orphanedIdentifiers: OrphanedIdentifier[] = [
  { id: "o1", sdkIdentifier: "acme_legacy", firstSeenAt: "2026-03-18T10:00:00Z", eventCount: 89, unattributedCost: 12_400_000 },
  { id: "o2", sdkIdentifier: "test_user_001", firstSeenAt: "2026-03-20T14:30:00Z", eventCount: 41, unattributedCost: 5_200_000 },
  { id: "o3", sdkIdentifier: "clearview_v2", firstSeenAt: "2026-03-22T09:15:00Z", eventCount: 12, unattributedCost: 1_850_000 },
];

export const mockCustomerMappingData: CustomerMappingData = {
  syncStatus: {
    connected: true,
    lastSyncAt: minutesAgo(14),
    syncing: false,
  },
  stats: {
    totalCustomers: 23,
    mapped: 21,
    unmapped: 2,
    orphanedEvents: 142,
    orphanedIdentifiers: 3,
    newCustomersSinceLastSync: 2,
  },
  customers,
  orphanedIdentifiers,
};
