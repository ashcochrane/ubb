// src/features/billing/components/change-history.tsx
import type { MarginChange, MarginLevel } from "../api/types";
import { cn } from "@/lib/utils";

interface ChangeHistoryProps {
  changes: MarginChange[];
}

const levelBadgeStyles: Record<MarginLevel, string> = {
  default: "bg-accent-light text-accent-text",
  product: "bg-blue-light text-blue-text",
  card: "bg-bg-subtle text-text-secondary border border-border",
};

export function ChangeHistory({ changes }: ChangeHistoryProps) {
  if (changes.length === 0) return null;

  return (
    <div>
      <h2 className="mb-2.5 text-[15px] font-bold text-text-primary">Change history</h2>
      <div className="overflow-hidden rounded-md border border-border bg-bg-surface">
        <div className="border-b border-border bg-bg-subtle px-4 py-2.5 text-[12px] font-semibold text-text-secondary">
          All margin changes
        </div>
        {changes.map((ch) => (
          <div key={ch.id} className="flex items-start justify-between gap-4 border-b border-bg-subtle px-4 py-3.5 last:border-0 hover:bg-bg-subtle">
            <div className="flex-1">
              <div className="mb-1.5 flex items-center gap-1.5">
                <span className={cn("inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold", levelBadgeStyles[ch.level])}>
                  {ch.level === "default" ? "Default" : ch.level === "product" ? "Product" : "Card"}
                </span>
                <span className="text-[13px] font-medium text-text-primary">{ch.targetName}</span>
              </div>
              <div className="text-[12px] text-text-primary">{ch.description}</div>
              <div className="mt-1 text-[11px] italic text-text-secondary">
                &ldquo;{ch.reason}&rdquo;
              </div>
              <div className="mt-1 text-[11px] text-text-muted">
                {new Date(ch.createdAt).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}
                {" · "}{ch.appliedBy}
                {ch.effectiveness === "scheduled" && ch.effectiveDate && (
                  <span> · Scheduled for {new Date(ch.effectiveDate).toLocaleDateString("en-GB", { day: "numeric", month: "short" })}</span>
                )}
              </div>
            </div>
            <div className="shrink-0 text-right">
              {ch.estimatedImpact === 0 ? (
                <div className="text-[13px] font-bold text-text-muted">&mdash;</div>
              ) : (
                <div className={cn(
                  "text-[13px] font-bold",
                  ch.estimatedImpact > 0 ? "text-accent-text" : "text-green-text",
                )}>
                  {ch.estimatedImpact >= 0 ? "+" : ""}${ch.estimatedImpact}/mo
                </div>
              )}
              <div className="mt-0.5 text-[10px] text-text-muted">est. impact</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
