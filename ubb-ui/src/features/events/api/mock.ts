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

// In-memory audit trail (mutable so pushEvents can append)
let _auditEntries: AuditEntry[] = [...mockAuditEntries];

export async function getFilterOptions(): Promise<EventFilterOptions> {
  await mockDelay();
  return structuredClone(mockFilterOptions);
}

export async function getEvents(filters: EventFilters): Promise<EventsListResponse> {
  await mockDelay();
  const allEvents = generateMockEvents(25);

  let totalCount = 247614;
  let totalCostMicros = 4_218_230_000; // ~$4,218.23

  if (filters.customerId) {
    totalCount = Math.round(totalCount / 10);
    totalCostMicros = Math.round(totalCostMicros / 10);
  }
  if (filters.group === null) {
    // ungrouped filter
    totalCount = 142;
    totalCostMicros = 4_870_000; // ~$4.87
  } else if (filters.group) {
    totalCount = Math.round(totalCount * 0.33);
    totalCostMicros = Math.round(totalCostMicros * 0.33);
  }
  if (filters.cardSlug) {
    totalCount = Math.round(totalCount * 0.4);
    totalCostMicros = Math.round(totalCostMicros * 0.4);
  }

  // Apply date filter: just return same events (mock ignores date range but passes it through)
  void filters.dateFrom;
  void filters.dateTo;

  return {
    events: allEvents,
    totalCount,
    totalCostMicros,
    nextCursor: totalCount > 25 ? "cursor-page-2" : null,
    hasMore: totalCount > 25,
  };
}

export async function pushEvents(
  events: StagedEvent[],
  reason: string,
): Promise<PushResult> {
  await mockDelay(800);
  const batchId = `audit-${Date.now()}`;
  const newEntry: AuditEntry = {
    id: batchId,
    action: "added",
    reason,
    rowCount: events.length,
    author: "current.user@example.com",
    createdAt: new Date().toISOString(),
    reversedAt: null,
  };
  _auditEntries = [newEntry, ..._auditEntries];
  return {
    pushedCount: events.length,
    batchId,
  };
}

export async function getAuditTrail(): Promise<AuditEntry[]> {
  await mockDelay();
  return structuredClone(_auditEntries);
}

export async function reverseAuditEntry(entryId: string): Promise<void> {
  await mockDelay(600);
  _auditEntries = _auditEntries.map((e) =>
    e.id === entryId
      ? { ...e, action: "reversed" as const, reversedAt: new Date().toISOString() }
      : e,
  );
}

export async function exportCsv(filters: EventFilters): Promise<{ downloadUrl: string }> {
  await mockDelay(1200);
  void filters;
  return { downloadUrl: "#mock-download" };
}
