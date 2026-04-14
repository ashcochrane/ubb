import { useMemo } from "react";

interface ManualAllocationProps {
  dayLabels: string[];
  allocations: Record<string, number>;
  targetAmount: number;
  onChange: (label: string, value: number) => void;
}

export function ManualAllocation({ dayLabels, allocations, targetAmount, onChange }: ManualAllocationProps) {
  const maxValue = useMemo(
    () => Math.max(...dayLabels.map((l) => allocations[l] ?? 0), 0.01),
    [dayLabels, allocations],
  );

  const total = useMemo(
    () => dayLabels.reduce((sum, l) => sum + (allocations[l] ?? 0), 0),
    [dayLabels, allocations],
  );

  const remaining = Math.round((targetAmount - total) * 100) / 100;

  return (
    <div className="space-y-1.5">
      <div className="text-muted font-medium text-muted-foreground">Per-day allocation</div>
      <div className="max-h-[200px] space-y-1 overflow-y-auto rounded-md bg-bg-subtle px-3 py-2">
        {dayLabels.map((label) => {
          const value = allocations[label] ?? 0;
          const barWidth = maxValue > 0 ? (value / maxValue) * 100 : 0;
          return (
            <div key={label} className="flex items-center gap-2">
              <span className="w-[52px] shrink-0 text-muted text-muted-foreground">{label}</span>
              <div className="relative h-[18px] flex-1 overflow-hidden rounded-sm bg-accent/40">
                <div
                  className="absolute inset-y-0 left-0 rounded-sm"
                  style={{ width: `${barWidth}%`, backgroundColor: "#AFA9EC" }}
                />
              </div>
              <input
                type="number"
                step="any"
                min={0}
                value={value}
                onChange={(e) => onChange(label, parseFloat(e.target.value) || 0)}
                className="w-[72px] shrink-0 rounded-md border border-border bg-bg-surface px-2 py-0.5 text-right font-mono text-label outline-none focus:border-muted-foreground"
              />
            </div>
          );
        })}
      </div>

      <div className="flex justify-end">
        {remaining === 0 ? (
          <span className="rounded-full bg-green-light px-2.5 py-0.5 text-muted font-medium text-green-text">
            Fully allocated
          </span>
        ) : remaining > 0 ? (
          <span className="rounded-full bg-amber-light px-2.5 py-0.5 text-muted font-medium text-amber-text">
            ${remaining.toFixed(2)} remaining
          </span>
        ) : (
          <span className="rounded-full bg-red-light px-2.5 py-0.5 text-muted font-medium text-red-text">
            ${Math.abs(remaining).toFixed(2)} over-allocated
          </span>
        )}
      </div>
    </div>
  );
}
