// src/features/events/api/types.ts

export interface UsageEvent {
  id: string;
  timestamp: string; // ISO date-time
  customerKey: string;
  groupKey: string; // empty = ungrouped
  cardKey: string;
  dimension: string;
  quantity: number;
  unitPrice: number; // dollars per unit (e.g. 0.00000015)
  cost: number; // quantity * unitPrice in dollars
}

export interface StagedEvent {
  timestamp: string; // "YYYY-MM-DD" or ISO
  customerKey: string;
  groupKey: string;
  cardKey: string;
  dimension: string;
  quantity: number;
}

export interface ValidationError {
  field: "timestamp" | "customerKey" | "cardKey" | "dimension" | "quantity";
  message: string;
  warning?: boolean; // true = warning only, false = hard error
}

export interface EventFilters {
  dateFrom: string;
  dateTo: string;
  customerKey: string; // empty = all
  groupKey: string; // empty = all, "(ungrouped)" = ungrouped only
  cardKey: string; // empty = all
}

export interface EventsListResponse {
  events: UsageEvent[];
  totalCount: number;
  totalCostDollars: number;
  estimatedCsvBytes: number;
}

export interface FilterOption {
  key: string;
  eventCount: number;
}

export interface EventFilterOptions {
  customers: FilterOption[];
  groups: FilterOption[];
  cards: FilterOption[];
  ungroupedCount: number;
  /** Map of cardKey -> dimension keys available on that card */
  cardDimensions: Record<string, string[]>;
  /** Map of dimension -> unit price in dollars */
  dimensionPrices: Record<string, number>;
}

export type AuditAction = "added" | "edited" | "reversed";

export interface AuditEntry {
  id: string;
  action: AuditAction;
  title: string;
  reason?: string;
  rowCount: number;
  author: string;
  date: string; // ISO
  reversedDate?: string; // ISO, only if reversed
}

export interface PushResult {
  pushedCount: number;
  auditEntryId: string;
}
