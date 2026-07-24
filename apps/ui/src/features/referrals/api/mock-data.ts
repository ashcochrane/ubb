// Mock fixtures for the referrals surface — one coherent story:
// "Acme AI" runs a 10% revenue-share program (created March 2026) with four
// registered referrers in varying states: a productive one, one whose only
// referral was revoked, a brand-new one with no referrals yet, and a
// deactivated referrer that still accrues on an old referral.
//
// Module-level mutable state lets the mock provider simulate mutations
// coherently within a session; `resetReferralsMockState` exists for tests.

import type {
  LedgerEntryOut,
  MarginCustomerRow,
  ProgramOut,
  ReferralOut,
  ReferrerOut,
} from "./types";

/** Stable customer UUIDs (RFC-4122-valid so they pass form validation). */
export const MOCK_CUSTOMER_IDS = {
  acme: "a1b2c3d4-9f10-4e8b-b2aa-101010101001",
  nova: "b2c3d4e5-1a2b-4c3d-8e4f-202020202002",
  kite: "c3d4e5f6-2b3c-4d4e-9f50-303030303003",
  ember: "d4e5f6a7-3c4d-4e5f-a061-404040404004",
  spareOne: "e5f6a7b8-4d5e-4f60-b172-505050505005",
  spareTwo: "f6a7b8c9-5e6f-4a71-8283-606060606006",
} as const;

const EXTERNAL_IDS: Record<string, string> = {
  [MOCK_CUSTOMER_IDS.acme]: "acct-acme-labs",
  [MOCK_CUSTOMER_IDS.nova]: "acct-nova-agents",
  [MOCK_CUSTOMER_IDS.kite]: "acct-kite-ops",
  [MOCK_CUSTOMER_IDS.ember]: "acct-ember-co",
  [MOCK_CUSTOMER_IDS.spareOne]: "acct-cedar-ai",
  [MOCK_CUSTOMER_IDS.spareTwo]: "acct-harbor-ml",
};

export function externalIdFor(customerId: string): string {
  return EXTERNAL_IDS[customerId] ?? `acct-${customerId.slice(0, 8)}`;
}

export interface ReferralsMockState {
  program: ProgramOut | null;
  referrers: ReferrerOut[];
  /** Keyed by referrer customer_id. */
  referralsByReferrer: Record<string, ReferralOut[]>;
  /** Keyed by referral id. */
  ledgerByReferral: Record<string, LedgerEntryOut[]>;
  marginCustomers: MarginCustomerRow[];
}

function marginRow(customerId: string, revenue: number, cost: number): MarginCustomerRow {
  return {
    customer_id: customerId,
    usage_revenue_micros: revenue,
    usage_billed_micros: revenue,
    subscription_revenue_micros: 0,
    provider_cost_micros: cost,
    gross_margin_micros: revenue - cost,
    margin_percentage: revenue === 0 ? 0 : ((revenue - cost) / revenue) * 100,
  };
}

export function buildInitialState(): ReferralsMockState {
  return {
    program: {
      id: "prog-4f2a9c",
      reward_type: "revenue_share",
      reward_value: 10,
      attribution_window_days: 30,
      reward_window_days: 365,
      max_reward_micros: 500_000_000, // $500 lifetime cap per referral
      estimated_cost_percentage: 5,
      max_referrals_per_day: 50,
      min_customer_age_hours: 24,
      status: "active",
      created_at: "2026-03-02T09:15:00Z",
      updated_at: "2026-06-15T14:40:00Z",
    },
    referrers: [
      {
        id: "refr-0003",
        customer_id: MOCK_CUSTOMER_IDS.kite,
        referral_code: "REF-KITE9034",
        referral_link_token: "rlt_2b3c4d5e6f70",
        is_active: true,
        created_at: "2026-06-02T11:30:00Z",
      },
      {
        id: "refr-0002",
        customer_id: MOCK_CUSTOMER_IDS.nova,
        referral_code: "REF-NOVA4417",
        referral_link_token: "rlt_1a2b3c4d5e6f",
        is_active: true,
        created_at: "2026-04-11T16:05:00Z",
      },
      {
        id: "refr-0001",
        customer_id: MOCK_CUSTOMER_IDS.acme,
        referral_code: "REF-ACME8821",
        referral_link_token: "rlt_9f8e7d6c5b4a",
        is_active: true,
        created_at: "2026-03-05T10:12:00Z",
      },
      {
        id: "refr-0000",
        customer_id: MOCK_CUSTOMER_IDS.ember,
        referral_code: "REF-EMBER1276",
        referral_link_token: "rlt_0a1b2c3d4e5f",
        is_active: false,
        created_at: "2026-02-14T08:00:00Z",
      },
    ],
    referralsByReferrer: {
      [MOCK_CUSTOMER_IDS.acme]: [
        {
          id: "rfl-0002",
          referred_customer_id: "11aa22bb-33cc-4dd4-8ee5-901234567002",
          referred_external_id: "acct-blue-heron",
          referral_code_used: "REF-ACME8821",
          status: "active",
          reward_type: "revenue_share",
          total_earned_micros: 12_130_000,
          total_referred_spend_micros: 121_300_000,
          attributed_at: "2026-06-20T13:22:00Z",
          reward_window_ends_at: "2027-06-20T13:22:00Z",
        },
        {
          id: "rfl-0001",
          referred_customer_id: "11aa22bb-33cc-4dd4-8ee5-901234567001",
          referred_external_id: "acct-golden-fox",
          referral_code_used: "REF-ACME8821",
          status: "active",
          reward_type: "revenue_share",
          total_earned_micros: 84_500_000,
          total_referred_spend_micros: 845_000_000,
          attributed_at: "2026-04-02T09:45:00Z",
          reward_window_ends_at: "2027-04-02T09:45:00Z",
        },
        {
          id: "rfl-0003",
          referred_customer_id: "11aa22bb-33cc-4dd4-8ee5-901234567003",
          referred_external_id: "acct-copper-owl",
          referral_code_used: "REF-ACME8821",
          status: "expired",
          reward_type: "revenue_share",
          total_earned_micros: 21_000_000,
          total_referred_spend_micros: 210_000_000,
          attributed_at: "2026-03-10T15:00:00Z",
          reward_window_ends_at: "2026-07-08T15:00:00Z",
        },
      ],
      [MOCK_CUSTOMER_IDS.nova]: [
        {
          id: "rfl-0004",
          referred_customer_id: "11aa22bb-33cc-4dd4-8ee5-901234567004",
          referred_external_id: "acct-iron-wren",
          referral_code_used: "REF-NOVA4417",
          status: "revoked",
          reward_type: "revenue_share",
          total_earned_micros: 5_250_000,
          total_referred_spend_micros: 52_500_000,
          attributed_at: "2026-05-05T10:10:00Z",
          reward_window_ends_at: "2027-05-05T10:10:00Z",
        },
      ],
      [MOCK_CUSTOMER_IDS.kite]: [],
      [MOCK_CUSTOMER_IDS.ember]: [
        {
          id: "rfl-0005",
          referred_customer_id: "11aa22bb-33cc-4dd4-8ee5-901234567005",
          referred_external_id: "acct-silver-elk",
          referral_code_used: "REF-EMBER1276",
          status: "active",
          reward_type: "flat_fee",
          total_earned_micros: 40_070_000,
          total_referred_spend_micros: 400_700_000,
          attributed_at: "2026-05-28T12:00:00Z",
          reward_window_ends_at: null,
        },
      ],
    },
    ledgerByReferral: {
      "rfl-0001": [
        {
          id: "led-0103",
          period_start: "2026-07-01T00:00:00Z",
          period_end: "2026-07-22T00:00:00Z",
          referred_spend_micros: 250_000_000,
          raw_cost_micros: 132_000_000,
          reward_micros: 25_000_000,
          calculation_method: "revenue_share_capped",
          created_at: "2026-07-22T02:00:00Z",
        },
        {
          id: "led-0102",
          period_start: "2026-06-01T00:00:00Z",
          period_end: "2026-07-01T00:00:00Z",
          referred_spend_micros: 345_000_000,
          raw_cost_micros: 180_000_000,
          reward_micros: 34_500_000,
          calculation_method: "revenue_share",
          created_at: "2026-07-01T02:00:00Z",
        },
        {
          id: "led-0101",
          period_start: "2026-05-01T00:00:00Z",
          period_end: "2026-06-01T00:00:00Z",
          referred_spend_micros: 250_000_000,
          raw_cost_micros: 130_000_000,
          reward_micros: 25_000_000,
          calculation_method: "revenue_share",
          created_at: "2026-06-01T02:00:00Z",
        },
      ],
      "rfl-0002": [
        {
          id: "led-0201",
          period_start: "2026-06-20T00:00:00Z",
          period_end: "2026-07-01T00:00:00Z",
          referred_spend_micros: 121_300_000,
          raw_cost_micros: 60_650_000,
          reward_micros: 12_130_000,
          calculation_method: "revenue_share",
          created_at: "2026-07-01T02:00:00Z",
        },
      ],
    },
    marginCustomers: [
      marginRow(MOCK_CUSTOMER_IDS.acme, 1_200_000_000, 480_000_000),
      marginRow(MOCK_CUSTOMER_IDS.nova, 640_000_000, 300_000_000),
      marginRow(MOCK_CUSTOMER_IDS.kite, 210_000_000, 95_000_000),
      marginRow(MOCK_CUSTOMER_IDS.ember, 88_000_000, 61_000_000),
      marginRow(MOCK_CUSTOMER_IDS.spareOne, 540_000_000, 220_000_000),
      marginRow(MOCK_CUSTOMER_IDS.spareTwo, 130_000_000, 90_000_000),
    ],
  };
}

export let mockState: ReferralsMockState = buildInitialState();

/** Reset (or seed) the mock state — used by tests and nothing else. */
export function resetReferralsMockState(overrides?: Partial<ReferralsMockState>): void {
  mockState = { ...buildInitialState(), ...overrides };
}
