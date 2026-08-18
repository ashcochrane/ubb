// Mock fixtures for the developers feature. One coherent story: Acme AI has
// two live backend keys, one never-used key minted last week, and one revoked
// CI key; the sandbox exists with a single test key. Dates ~July 2026.

import type { ApiKey, MarginCustomerRow, SandboxStatus } from "./types";

export const MOCK_SANDBOX_TENANT_ID = "6b7c8d90-1234-4a5b-9c0d-e1f2a3b4c5d6";
export const MOCK_LIVE_TENANT_ID = "0a1b2c3d-9876-4e5f-8a9b-c0d1e2f3a4b5";

export const MOCK_API_KEYS: ApiKey[] = [
  {
    id: "3f9e1c2a-77aa-4b6e-9d21-0f8b6a5c4d3e",
    key_prefix: "ubb_live_w8Kd",
    label: "Reporting service",
    is_active: true,
    created_at: "2026-07-16T10:05:00Z",
    last_used_at: null,
  },
  {
    id: "b4c8e6f0-1122-4d3c-a5b6-778899aabbcc",
    key_prefix: "ubb_live_k3xA",
    label: "Production backend",
    is_active: true,
    created_at: "2026-03-14T09:12:00Z",
    last_used_at: "2026-07-23T18:40:00Z",
  },
  {
    id: "9d0e1f2a-3344-4b5c-8d9e-aabbccddeeff",
    key_prefix: "ubb_live_9fQz",
    label: "Staging worker",
    is_active: true,
    created_at: "2026-05-02T14:30:00Z",
    last_used_at: "2026-07-19T07:05:00Z",
  },
  {
    id: "5a6b7c8d-5566-4e9f-b0a1-223344556677",
    key_prefix: "ubb_live_p0Lm",
    label: "CI smoke tests (rotated)",
    is_active: false,
    created_at: "2026-01-20T11:00:00Z",
    last_used_at: "2026-04-30T23:59:00Z",
  },
];

export const MOCK_SANDBOX: SandboxStatus = {
  exists: true,
  sandbox_tenant_id: MOCK_SANDBOX_TENANT_ID,
  key_prefixes: ["ubb_test_4dKe"],
};

export const MOCK_MARGIN_CUSTOMERS: MarginCustomerRow[] = [
  {
    customer_id: "c1a2b3d4-0001-4abc-9def-000000000001",
    subscription_revenue_micros: 49_000_000,
    usage_billed_micros: 182_500_000,
    usage_revenue_micros: 182_500_000,
    provider_cost_micros: 96_200_000,
    unresolved_event_count: 0,
    unpriced_event_count: 0,
    gross_margin_micros: 135_300_000,
    margin_percentage: 58.4,
  },
  {
    customer_id: "c1a2b3d4-0002-4abc-9def-000000000002",
    subscription_revenue_micros: 0,
    usage_billed_micros: 64_100_000,
    usage_revenue_micros: 64_100_000,
    provider_cost_micros: 41_800_000,
    unresolved_event_count: 0,
    unpriced_event_count: 0,
    gross_margin_micros: 22_300_000,
    margin_percentage: 34.8,
  },
  {
    customer_id: "c1a2b3d4-0003-4abc-9def-000000000003",
    subscription_revenue_micros: 99_000_000,
    usage_billed_micros: 12_400_000,
    usage_revenue_micros: 12_400_000,
    provider_cost_micros: 18_900_000,
    unresolved_event_count: 0,
    unpriced_event_count: 0,
    gross_margin_micros: 92_500_000,
    margin_percentage: 83.0,
  },
];

/**
 * The mock wallet the test console draws down: starts at $12.50. A test
 * event whose billed cost pushes the balance below zero returns the stop
 * verdict (customer_floor / customer) — the teaching scenario.
 */
export const MOCK_STARTING_BALANCE_MICROS = 12_500_000;

/** Measurement keys the mock "cost cards" cover; anything else is uncosted. */
export const MOCK_COSTED_MEASUREMENTS = new Set([
  "tokens_in",
  "tokens_out",
  "requests",
]);

/** Per-measurement mock prices (micros per unit). */
export const MOCK_MEASUREMENT_RATE_MICROS: Record<string, number> = {
  tokens_in: 2,
  tokens_out: 6,
  requests: 50_000,
};

const KEY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789";

function randomChunk(length: number): string {
  let out = "";
  for (let i = 0; i < length; i++) {
    out += KEY_ALPHABET[Math.floor(Math.random() * KEY_ALPHABET.length)] ?? "x";
  }
  return out;
}

/** A plausible key prefix like "ubb_live_x7Qm". */
export function mockKeyPrefix(mode: "live" | "test"): string {
  return `ubb_${mode}_${randomChunk(4)}`;
}

/** A plausible full raw key for the given prefix. */
export function mockRawKey(prefix: string): string {
  return `${prefix}${randomChunk(28)}`;
}
