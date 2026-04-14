// src/features/events/api/api.ts

import { platformApi } from "@/api/client";
import type {
  AuditEntry,
  EventFilterOptions,
  EventFilters,
  EventsListResponse,
  PushResult,
  StagedEvent,
} from "./types";

export async function getFilterOptions(): Promise<EventFilterOptions> {
  const { data } = await platformApi.GET("/events/filter-options", {});
  return data as EventFilterOptions;
}

export async function getEvents(filters: EventFilters): Promise<EventsListResponse> {
  const { data } = await platformApi.POST("/events/list", { body: filters });
  return data as EventsListResponse;
}

export async function pushEvents(
  events: StagedEvent[],
  reason: string,
): Promise<PushResult> {
  const { data } = await platformApi.POST("/events/push", {
    body: { events, reason },
  });
  return data as PushResult;
}

export async function getAuditTrail(): Promise<AuditEntry[]> {
  const { data } = await platformApi.GET("/events/audit-trail", {});
  return data as AuditEntry[];
}

export async function reverseAuditEntry(entryId: string): Promise<void> {
  await platformApi.POST("/events/audit-trail/{entryId}/reverse", {
    params: { path: { entryId } },
  });
}

export async function exportCsv(filters: EventFilters): Promise<{ downloadUrl: string }> {
  const { data } = await platformApi.POST("/events/export", { body: filters });
  return data as { downloadUrl: string };
}
