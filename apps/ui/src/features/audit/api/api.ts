import { auditApi } from "@/api/client";
import { requireData } from "@/api/errors";
import type { CursorPage } from "@/lib/use-cursor-list";
import type { AuditRecord, AuditFilters } from "./types";

export function listAuditRecords(
  params: AuditFilters & { cursor?: string; limit?: number },
): Promise<CursorPage<AuditRecord>> {
  return auditApi
    .GET("/records", { params: { query: params } })
    .then((r) => requireData(r, "Failed to load audit records"));
}
