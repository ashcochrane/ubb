import { cn } from "@/lib/utils";
import { formatShortDate } from "@/lib/format";
import type { AuditEntry } from "../api/types";

interface AuditTrailProps {
  entries: AuditEntry[];
  onViewBatch: (entryId: string) => void;
  onReverseBatch: (entryId: string) => void;
  reversingId: string | null;
}

const ACTION_STYLES: Record<string, { pill: string; label: string }> = {
  added: { pill: "bg-blue-light text-blue-text", label: "Added" },
  reversed: { pill: "bg-red-light text-red-text", label: "Reversed" },
};

function deriveTitle(entry: AuditEntry): string {
  const verb = entry.action === "added" ? "Added" : "Reversed";
  return `${verb} ${entry.rowCount} event${entry.rowCount !== 1 ? "s" : ""}`;
}

export function AuditTrail({
  entries,
  onViewBatch,
  onReverseBatch,
  reversingId,
}: AuditTrailProps) {
  return (
    <div className="rounded-md border border-border bg-bg-surface px-4 py-3.5">
      <h3 className="mb-3 text-[13px] font-semibold text-muted-foreground">Change history</h3>
      <div className="space-y-2">
        {entries.map((entry) => {
          const isReversed = entry.action === "reversed";
          const style = ACTION_STYLES[entry.action] ?? ACTION_STYLES.added!;
          const isReversingThis = reversingId === entry.id;
          const title = deriveTitle(entry);

          return (
            <div
              key={entry.id}
              className={cn(
                "rounded-md border border-border transition-colors hover:bg-bg-page",
                isReversed && "opacity-50",
              )}
            >
              <div className="grid grid-cols-[1fr_auto] items-center gap-2 px-3.5 py-2.5">
                <div>
                  <div className="flex items-center gap-1.5">
                    <span className={cn("inline-block rounded-full px-2 py-0.5 text-muted font-medium", style.pill)}>
                      {style.label}
                    </span>
                    <span className={cn("text-[12px] font-medium", isReversed && "line-through")}>
                      {title}
                    </span>
                  </div>
                  {entry.reason && (
                    <div className="mt-0.5 text-label text-text-secondary">{entry.reason}</div>
                  )}
                  <div className="mt-0.5 text-muted text-text-muted">
                    {formatShortDate(entry.createdAt)}
                    {entry.author && ` by ${entry.author}`}
                    {entry.reversedAt && ` \u2014 Reversed ${formatShortDate(entry.reversedAt)}`}
                  </div>
                </div>
                <div className="text-right">
                  <div className={cn("font-mono text-label text-text-secondary", isReversed && "line-through")}>
                    {entry.rowCount} rows
                  </div>
                  {!isReversed && (
                    <div className="mt-1 flex gap-1">
                      <button
                        className="rounded-full border border-border-mid px-2.5 py-0.5 text-muted text-text-secondary hover:bg-bg-subtle"
                        onClick={() => onViewBatch(entry.id)}
                      >
                        View
                      </button>
                      <button
                        className="rounded-full border border-red-border px-2.5 py-0.5 text-muted text-red-text hover:bg-red-light"
                        onClick={() => onReverseBatch(entry.id)}
                        disabled={isReversingThis}
                      >
                        {isReversingThis ? "Reversing..." : "Reverse"}
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
