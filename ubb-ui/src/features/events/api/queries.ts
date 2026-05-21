// src/features/events/api/queries.ts

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toastOnError } from "@/lib/mutations";
import { eventsApi } from "./provider";
import type { EventFilters, StagedEvent } from "./types";

export function useEventFilterOptions() {
  return useQuery({
    queryKey: ["event-filter-options"],
    queryFn: () => eventsApi.getFilterOptions(),
    staleTime: 5 * 60 * 1000,
  });
}

export function useEvents(filters: EventFilters | null) {
  return useQuery({
    queryKey: ["events", filters],
    queryFn: () => eventsApi.getEvents(filters!),
    enabled: filters !== null,
    placeholderData: (prev) => prev,
  });
}

export function useAuditTrail() {
  return useQuery({
    queryKey: ["events-audit-trail"],
    queryFn: () => eventsApi.getAuditTrail(),
  });
}

export function usePushEvents() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ events, reason }: { events: StagedEvent[]; reason: string }) =>
      eventsApi.pushEvents(events, reason),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["events"] });
      void qc.invalidateQueries({ queryKey: ["events-audit-trail"] });
    },
    onError: toastOnError("Couldn't push events"),
  });
}

export function useReverseAuditEntry() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (entryId: string) => eventsApi.reverseAuditEntry(entryId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["events-audit-trail"] });
    },
    onError: toastOnError("Couldn't reverse batch"),
  });
}

export function useExportEventsCsv() {
  return useMutation({
    mutationFn: (filters: EventFilters) => eventsApi.exportCsv(filters),
    onError: toastOnError("Couldn't generate export"),
  });
}
