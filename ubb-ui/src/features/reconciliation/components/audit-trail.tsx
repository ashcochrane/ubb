// src/features/reconciliation/components/audit-trail.tsx
import type { AuditEntry } from "../api/types";
import { cn } from "@/lib/utils";

interface AuditTrailProps {
  entries: AuditEntry[];
}

const typeStyles: Record<string, string> = {
  period_insert: "bg-blue-light text-blue-text",
  boundary_shift: "bg-muted text-muted-foreground",
  price_edit: "bg-amber-light text-amber-text",
  credit_recorded: "bg-purple-light text-purple-text",
};

const typeLabels: Record<string, string> = {
  period_insert: "Period insert",
  boundary_shift: "Boundary shift",
  price_edit: "Price edit",
  credit_recorded: "Credit recorded",
};

export function AuditTrail({ entries }: AuditTrailProps) {
  if (entries.length === 0) return null;

  return (
    <div className="rounded-md border border-border bg-bg-surface px-4 py-3.5">
      <h3 className="mb-3 text-[13px] font-semibold text-muted-foreground">Audit trail</h3>
      <div className="space-y-3">
        {entries.map((entry) => (
          <div key={entry.id} className="flex items-start justify-between gap-4">
            <div>
              <span className={cn(
                "inline-block rounded-full px-2 py-0.5 text-muted font-medium",
                typeStyles[entry.type] ?? "bg-muted text-muted-foreground",
              )}>
                {typeLabels[entry.type] ?? entry.type}
              </span>
              <div className="mt-1 text-label">{entry.title}</div>
              <div className="text-label text-muted-foreground">{entry.description}</div>
              <div className="mt-0.5 text-muted text-muted-foreground/60">{entry.metadata}</div>
            </div>
            <div className="text-right">
              <div
                className={cn(
                  "font-mono text-[12px] font-semibold",
                  entry.delta > 0 ? "text-red-text" : "text-green-text",
                )}
              >
                {entry.delta > 0 ? "+" : ""}${entry.delta.toFixed(2)}
              </div>
              <div className="text-muted text-muted-foreground">{entry.deltaLabel}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
