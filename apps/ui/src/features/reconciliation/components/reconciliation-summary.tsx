// src/features/reconciliation/components/reconciliation-summary.tsx
import { cn } from "@/lib/utils";

interface ReconciliationSummaryProps {
  original: number;
  reconciled: number;
  delta: number;
}

export function ReconciliationSummary({ original, reconciled, delta }: ReconciliationSummaryProps) {
  const isPositive = delta > 0;

  return (
    <div className="flex items-center justify-between rounded-md border border-border bg-bg-surface px-3.5 py-2.5">
      <span className="text-[12px] text-muted-foreground">All-time reconciled cost</span>
      <div className="flex items-baseline gap-2.5">
        <span className="font-mono text-[13px] text-muted-foreground line-through">
          ${original.toLocaleString()}
        </span>
        <span className="font-mono text-[15px] font-bold">
          ${reconciled.toLocaleString()}
        </span>
        <span
          className={cn(
            "rounded-full px-2 py-0.5 font-mono text-label font-medium",
            isPositive
              ? "bg-red-light text-red-text"
              : "bg-green-light text-green-text",
          )}
        >
          {isPositive ? "+" : ""}${delta.toFixed(2)}
        </span>
      </div>
    </div>
  );
}
