import { useCursorList } from "@/lib/use-cursor-list";
import * as api from "./api";
import type { AuditFilters } from "./types";

/** Only send non-empty filter values so blank inputs don't constrain the query. */
function cleanFilters(filters: AuditFilters): AuditFilters {
  const out: AuditFilters = {};
  if (filters.action?.trim()) out.action = filters.action.trim();
  if (filters.resource_type?.trim()) out.resource_type = filters.resource_type.trim();
  if (filters.resource_id?.trim()) out.resource_id = filters.resource_id.trim();
  return out;
}

export function useAuditRecords(filters: AuditFilters) {
  const clean = cleanFilters(filters);
  return useCursorList({
    // Filters are part of the key so the pager resets when they change.
    queryKeyBase: ["audit", "records", clean],
    fetchPage: (cursor) => api.listAuditRecords({ ...clean, cursor, limit: 50 }),
  });
}
