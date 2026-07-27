import type { AuditSchemas } from "@/api/types";

export type AuditRecord = AuditSchemas["AuditRecordOut"];

/** Filters accepted by GET /audit/records (all optional). */
export interface AuditFilters {
  action?: string;
  resource_type?: string;
  resource_id?: string;
}
