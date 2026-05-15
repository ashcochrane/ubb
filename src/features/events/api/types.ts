export interface UsageEvent {
  id: string;
  effectiveAt: string;
  customerId: string;
  customerExternalId: string;
  group: string | null;
  cardId: string | null;
  cardSlug: string | null;
  cardName: string | null;
  provider: string;
  usageMetrics: Record<string, number>;
  providerCostMicros: number | null;
  billedCostMicros: number | null;
}

export interface StagedEvent {
  // UI-only: backend sets effective_at via auto_now_add; this is for staging display only
  effectiveAt: string;
  customerExternalId: string;
  group: string;
  pricingCard: string;  // was: cardSlug — backend expects pricing_card (camelCase: pricingCard)
  usageMetrics: Record<string, number>;
  idempotencyKey?: string;
}

export interface ValidationError {
  field: "effectiveAt" | "customerExternalId" | "pricingCard" | "usageMetrics" | "quantity";
  message: string;
  warning?: boolean;
}

export interface EventFilters {
  dateFrom?: string;
  dateTo?: string;
  customerId?: string;
  group?: string | null; // null = filter to ungrouped events only
  cardSlug?: string;
  cursor?: string;
  limit?: number;
}

export interface EventsListResponse {
  events: UsageEvent[];
  totalCount: number;
  totalCostMicros: number;
  nextCursor: string | null;
  hasMore: boolean;
}

export interface FilterOption {
  key: string;
  eventCount: number;
}

export interface DimensionPriceInfo {
  costPerUnitMicros: number;
  unitQuantity: number;
  pricingType: string;
}

export interface EventFilterOptions {
  customers: FilterOption[];
  groups: FilterOption[];
  cards: FilterOption[];
  ungroupedCount: number;
  cardDimensions: Record<string, string[]>; // cardSlug -> [metricName]
  dimensionPrices: Record<string, DimensionPriceInfo>;  // metricName -> price info object
}

export type AuditAction = "added" | "reversed";

export interface AuditEntry {
  id: string;
  action: AuditAction;
  reason: string;
  rowCount: number;
  author: string;
  createdAt: string;
  reversedAt: string | null;
}

export interface PushResult {
  pushedCount: number;
  batchId: string;
}
