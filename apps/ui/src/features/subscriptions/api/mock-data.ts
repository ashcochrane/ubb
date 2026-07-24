// Mock fixtures for the subscriptions surface (coherent July-2026 story:
// Acme AI is fully Stripe-onboarded and sells three plans).

import type { ConnectStatus, PlanOut, SyncResponse } from "./types";

export const MOCK_CONNECT_STATUS: ConnectStatus = {
  account_id: "acct_1QxTAcmeMock42",
  charges_enabled: true,
  onboarded: true,
};

/** Plans "already created" by the tenant — the API can't list these back. */
export const MOCK_PLANS: PlanOut[] = [
  {
    id: "0d9f5c2e-4a1b-4f7e-9c3d-1a2b3c4d5e6f",
    key: "starter-monthly",
    name: "Starter",
    access_fee_micros: 29_000_000,
    per_seat_micros: 0,
    interval: "month",
  },
  {
    id: "7b8a9c0d-1e2f-4a3b-8c4d-5e6f7a8b9c0d",
    key: "team-monthly",
    name: "Team",
    access_fee_micros: 99_000_000,
    per_seat_micros: 15_000_000,
    interval: "month",
  },
  {
    id: "3c4d5e6f-7a8b-4c9d-a0e1-f2a3b4c5d6e7",
    key: "team-annual",
    name: "Team (annual)",
    access_fee_micros: 990_000_000,
    per_seat_micros: 150_000_000,
    interval: "year",
  },
];

export const MOCK_SYNC_RESULT: SyncResponse = {
  synced: 14,
  skipped: 3,
  errors: 0,
};
