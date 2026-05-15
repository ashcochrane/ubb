// src/features/events/api/mock-data.ts

import type { AuditEntry, DimensionPriceInfo, EventFilterOptions, UsageEvent } from "./types";

export const CUSTOMERS = [
  "acme_corp",
  "brightpath",
  "novatech",
  "helios",
  "clearview",
  "eko",
  "pinnacle",
  "meridian",
] as const;

const CUSTOMER_IDS: Record<string, string> = {
  acme_corp: "cust-001",
  brightpath: "cust-002",
  novatech: "cust-003",
  helios: "cust-004",
  clearview: "cust-005",
  eko: "cust-006",
  pinnacle: "cust-007",
  meridian: "cust-008",
};

const CUSTOMER_COUNTS = [14219, 11402, 6841, 9403, 8210, 7891, 2104, 3812];

export const GROUPS = [
  "research_agent",
  "doc_processor",
  "chat",
  "content_gen",
  "competitor_monitor",
] as const;

const GROUP_COUNTS = [82419, 34210, 21080, 8920, 1204];

export const CARDS = [
  "gemini_2_flash",
  "claude_sonnet",
  "gpt_4o",
  "serper",
  "google_places",
] as const;

const CARD_IDS: Record<string, string> = {
  gemini_2_flash: "card-001",
  claude_sonnet: "card-002",
  gpt_4o: "card-003",
  serper: "card-004",
  google_places: "card-005",
};

const CARD_NAMES: Record<string, string> = {
  gemini_2_flash: "Gemini 2 Flash",
  claude_sonnet: "Claude Sonnet",
  gpt_4o: "GPT-4o",
  serper: "Serper Search",
  google_places: "Google Places",
};

const CARD_COUNTS = [136240, 62100, 29960, 12400, 6914];

export const CARD_DIMENSIONS: Record<string, string[]> = {
  gemini_2_flash: ["input_tokens", "output_tokens", "grounding_requests"],
  claude_sonnet: ["input_tokens", "output_tokens"],
  gpt_4o: ["input_tokens", "output_tokens"],
  serper: ["search_queries"],
  google_places: ["requests"],
};

export const DIMENSION_PRICES: Record<string, DimensionPriceInfo> = {
  input_tokens:        { costPerUnitMicros: 150,   unitQuantity: 1, pricingType: "per_unit" },
  output_tokens:       { costPerUnitMicros: 400,   unitQuantity: 1, pricingType: "per_unit" },
  grounding_requests:  { costPerUnitMicros: 35000, unitQuantity: 1, pricingType: "per_unit" },
  search_queries:      { costPerUnitMicros: 35000, unitQuantity: 1, pricingType: "per_unit" },
  requests:            { costPerUnitMicros: 32000, unitQuantity: 1, pricingType: "per_unit" },
};

export const mockFilterOptions: EventFilterOptions = {
  customers: CUSTOMERS.map((key, i) => ({ key, eventCount: CUSTOMER_COUNTS[i]! })),
  groups: GROUPS.map((key, i) => ({ key, eventCount: GROUP_COUNTS[i]! })),
  cards: CARDS.map((key, i) => ({ key, eventCount: CARD_COUNTS[i]! })),
  ungroupedCount: 142,
  cardDimensions: CARD_DIMENSIONS,
  dimensionPrices: DIMENSION_PRICES,
};

/** Generate a page of mock usage events (one event per API call, multi-metric). */
export function generateMockEvents(count = 25): UsageEvent[] {
  const events: UsageEvent[] = [];
  const base = new Date(2026, 2, 20, 14, 23, 0);

  for (let i = 0; i < count; i++) {
    const t = new Date(base.getTime() - i * 62000);
    const customerExternalId = CUSTOMERS[Math.floor(Math.random() * CUSTOMERS.length)]!;
    const cardSlug = CARDS[Math.floor(Math.random() * CARDS.length)]!;
    const group = Math.random() > 0.06
      ? GROUPS[Math.floor(Math.random() * GROUPS.length)]!
      : null;

    const dims = CARD_DIMENSIONS[cardSlug]!;
    const usageMetrics: Record<string, number> = {};
    let providerCostMicros = 0;
    for (const d of dims) {
      const q = d.includes("token")
        ? Math.floor(Math.random() * 8000 + 200)
        : Math.floor(Math.random() * 3 + 1);
      usageMetrics[d] = q;
      providerCostMicros += q * (DIMENSION_PRICES[d]?.costPerUnitMicros ?? 0);
    }
    const billedCostMicros = Math.round(providerCostMicros * 1.25); // 25% margin

    events.push({
      id: `evt-${String(i).padStart(6, "0")}`,
      effectiveAt: t.toISOString(),
      customerId: CUSTOMER_IDS[customerExternalId] ?? "cust-000",
      customerExternalId,
      group,
      cardId: CARD_IDS[cardSlug] ?? null,
      cardSlug,
      cardName: CARD_NAMES[cardSlug] ?? null,
      provider: "openai",
      usageMetrics,
      providerCostMicros: Math.round(providerCostMicros),
      billedCostMicros,
    });
  }

  return events;
}

export const mockAuditEntries: AuditEntry[] = [
  {
    id: "audit-001",
    action: "added",
    reason: "Backfilling untracked Serper calls from INV-2026-0342.",
    rowCount: 47,
    author: "j.smith@acmecorp.com",
    createdAt: "2026-03-20T10:30:00Z",
    reversedAt: null,
  },
  {
    id: "audit-003",
    action: "reversed",
    reason: "Test data removed after environment reset.",
    rowCount: 12,
    author: "j.smith@acmecorp.com",
    createdAt: "2026-03-15T09:00:00Z",
    reversedAt: "2026-03-16T08:45:00Z",
  },
];
