// src/features/events/api/mock.ts

import { mockDelay } from "@/lib/api-provider";
import type {
  AuditEntry,
  EventFilterOptions,
  EventFilters,
  EventsListResponse,
  PushResult,
  StagedEvent,
} from "./types";
import {
  generateMockEvents,
  mockAuditEntries,
  mockFilterOptions,
} from "./mock-data";

export async function getFilterOptions(): Promise<EventFilterOptions> {
  await mockDelay();
  return structuredClone(mockFilterOptions);
}

export async function getEvents(filters: EventFilters): Promise<EventsListResponse> {
  await mockDelay();
  const allEvents = generateMockEvents(25);

  let totalCount = 247614;
  let totalCostDollars = 4218.23;

  if (filters.customerKey) {
    totalCount = Math.round(totalCount / 10);
    totalCostDollars = Math.round(totalCostDollars / 10 * 100) / 100;
  }
  if (filters.groupKey === "(ungrouped)") {
    totalCount = 142;
    totalCostDollars = 4.87;
  } else if (filters.groupKey) {
    totalCount = Math.round(totalCount * 0.33);
    totalCostDollars = Math.round(totalCostDollars * 0.33 * 100) / 100;
  }
  if (filters.cardKey) {
    totalCount = Math.round(totalCount * 0.4);
    totalCostDollars = Math.round(totalCostDollars * 0.4 * 100) / 100;
  }

  const estimatedCsvBytes = Math.max(100, totalCount * 75);

  return {
    events: allEvents,
    totalCount,
    totalCostDollars,
    estimatedCsvBytes,
  };
}

export async function pushEvents(
  events: StagedEvent[],
  reason: string,
): Promise<PushResult> {
  void reason;
  await mockDelay(800);
  return {
    pushedCount: events.length,
    auditEntryId: `audit-${Date.now()}`,
  };
}

export async function getAuditTrail(): Promise<AuditEntry[]> {
  await mockDelay();
  return structuredClone(mockAuditEntries);
}

export async function reverseAuditEntry(entryId: string): Promise<void> {
  await mockDelay(600);
  void entryId;
}

export async function exportCsv(filters: EventFilters): Promise<{ downloadUrl: string }> {
  await mockDelay(1200);
  void filters;
  return { downloadUrl: "#mock-download" };
}
