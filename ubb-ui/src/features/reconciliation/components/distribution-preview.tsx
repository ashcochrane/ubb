// src/features/reconciliation/components/distribution-preview.tsx
import { useMemo } from "react";

interface DistributionPreviewProps {
  mode: "lump_sum" | "even_daily" | "proportional" | "manual";
  amount: number;
  startDate: string;
  endDate: string;
  manualAllocations?: Record<string, number>;
}

function getDayLabels(start: string, end: string): string[] {
  const labels: string[] = [];
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const s = new Date(start);
  const e = new Date(end);
  while (s <= e) {
    labels.push(`${s.getDate()} ${months[s.getMonth()]!}`);
    s.setDate(s.getDate() + 1);
  }
  return labels;
}

// Deterministic mock weights for proportional mode
const PROPORTIONAL_WEIGHTS = [18, 12, 22, 15, 28, 20, 14];

export function DistributionPreview({ mode, amount, startDate, endDate, manualAllocations }: DistributionPreviewProps) {
  const dayLabels = useMemo(() => getDayLabels(startDate, endDate), [startDate, endDate]);
  const dayCount = dayLabels.length;
  const absAmount = Math.abs(amount);

  const bars = useMemo(() => {
    if (dayCount === 0 || absAmount === 0) return [];
    switch (mode) {
      case "lump_sum":
        return [{ label: dayLabels[0]!, value: absAmount }];

      case "even_daily": {
        const daily = absAmount / dayCount;
        return dayLabels.map((l) => ({ label: l, value: Math.round(daily * 100) / 100 }));
      }

      case "proportional": {
        const weights = dayLabels.map(
          (_, i) => PROPORTIONAL_WEIGHTS[i % PROPORTIONAL_WEIGHTS.length]!,
        );
        const weightTotal = weights.reduce((a, b) => a + b, 0);
        return dayLabels.map((l, i) => ({
          label: l,
          value: Math.round((weights[i]! / weightTotal) * absAmount * 100) / 100,
        }));
      }

      case "manual":
        return dayLabels.map((l) => ({
          label: l,
          value: manualAllocations?.[l] ?? 0,
        }));
    }
  }, [mode, absAmount, dayLabels, dayCount, manualAllocations]);

  const maxValue = Math.max(...bars.map((b) => b.value), 0.01);

  if (bars.length === 0) return null;

  return (
    <div className="rounded-md bg-bg-subtle px-3 py-3">
      <div className="mb-2 text-muted font-medium text-muted-foreground">Preview</div>
      <div className="flex items-end gap-px" style={{ height: 60 }}>
        {bars.map((bar) => (
          <div key={bar.label} className="flex flex-1 flex-col items-center justify-end" style={{ height: "100%" }}>
            <span className="mb-0.5 font-mono text-[8px] text-muted-foreground">
              ${bar.value.toFixed(2)}
            </span>
            <div
              className="w-full rounded-t-sm"
              style={{
                height: `${(bar.value / maxValue) * 100}%`,
                backgroundColor: "#AFA9EC",
                minHeight: bar.value > 0 ? 2 : 0,
              }}
            />
            <span className="mt-0.5 text-[7px] text-muted-foreground">{bar.label.split(" ")[0]!}</span>
          </div>
        ))}
      </div>
      <div className="mt-1 text-right font-mono text-muted text-muted-foreground">
        Total: ${absAmount.toFixed(2)}
      </div>
    </div>
  );
}
