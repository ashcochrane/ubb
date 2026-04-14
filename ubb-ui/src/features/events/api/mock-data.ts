// src/features/events/api/mock-data.ts

import type { AuditEntry, EventFilterOptions, UsageEvent } from "./types";

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

const CARD_COUNTS = [136240, 62100, 29960, 12400, 6914];

export const CARD_DIMENSIONS: Record<string, string[]> = {
  gemini_2_flash: ["input_tokens", "output_tokens", "grounding_requests"],
  claude_sonnet: ["input_tokens", "output_tokens"],
  gpt_4o: ["input_tokens", "output_tokens"],
  serper: ["search_queries"],
  google_places: ["requests"],
};

export const DIMENSION_PRICES: Record<string, number> = {
  input_tokens: 0.00000015,
  output_tokens: 0.0000004,
  grounding_requests: 0.035,
  search_queries: 0.035,
  requests: 0.032,
};

export const mockFilterOptions: EventFilterOptions = {
  customers: CUSTOMERS.map((key, i) => ({ key, eventCount: CUSTOMER_COUNTS[i]! })),
  groups: GROUPS.map((key, i) => ({ key, eventCount: GROUP_COUNTS[i]! })),
  cards: CARDS.map((key, i) => ({ key, eventCount: CARD_COUNTS[i]! })),
  ungroupedCount: 142,
  cardDimensions: CARD_DIMENSIONS,
  dimensionPrices: DIMENSION_PRICES,
};

/** Generate a page of mock usage events. */
export function generateMockEvents(count = 25): UsageEvent[] {
  const events: UsageEvent[] = [];
  const base = new Date(2026, 2, 20, 14, 23, 0);

  let eventIdx = 0;
  for (let i = 0; i < count; i++) {
    const t = new Date(base.getTime() - i * 62000);
    const c = CUSTOMERS[Math.floor(Math.random() * CUSTOMERS.length)]!;
    const k = CARDS[Math.floor(Math.random() * CARDS.length)]!;
    const g = Math.random() > 0.06
      ? GROUPS[Math.floor(Math.random() * GROUPS.length)]!
      : "";

    const dims = CARD_DIMENSIONS[k]!;
    for (const d of dims) {
      const q = d.includes("token")
        ? Math.floor(Math.random() * 8000 + 200)
        : Math.floor(Math.random() * 3 + 1);
      const unitPrice = DIMENSION_PRICES[d]!;
      events.push({
        id: `evt-${String(eventIdx++).padStart(6, "0")}`,
        timestamp: t.toISOString(),
        customerKey: c,
        groupKey: g,
        cardKey: k,
        dimension: d,
        quantity: q,
        unitPrice,
        cost: q * unitPrice,
      });
    }
  }

  return events;
}

export const mockAuditEntries: AuditEntry[] = [
  {
    id: "audit-001",
    action: "added",
    title: "47 events \u2014 invoice reconciliation",
    reason: "Backfilling untracked Serper calls from INV-2026-0342.",
    rowCount: 47,
    author: "j.smith@acmecorp.com",
    date: "2026-03-20T10:30:00Z",
  },
  {
    id: "audit-002",
    action: "edited",
    title: "23 events \u2014 customer changed",
    reason: "acme_legacy corrected to acme_corp.",
    rowCount: 23,
    author: "j.smith@acmecorp.com",
    date: "2026-03-18T14:20:00Z",
  },
  {
    id: "audit-003",
    action: "reversed",
    title: "12 events \u2014 test data removed",
    rowCount: 12,
    author: "j.smith@acmecorp.com",
    date: "2026-03-15T09:00:00Z",
    reversedDate: "2026-03-16T08:45:00Z",
  },
];
