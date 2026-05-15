import { ChartCard } from "@/components/shared/chart-card";
import { formatCostMicros } from "@/lib/format";
import { cn } from "@/lib/utils";
import type { GroupBreakdown } from "../api/types";

// Client-side color palette — assigned by index, never from the API.
const COLOR_PALETTE = [
  "#4a7fa8",
  "#6a5aaa",
  "#b84848",
  "#a16a4a",
  "#b5ad9e",
  "#3a8050",
  "#9a8e80",
];

function paletteColor(index: number): string {
  return COLOR_PALETTE[index % COLOR_PALETTE.length]!;
}

interface BreakdownCardProps {
  title: string;
  items: GroupBreakdown[];
  /** Optional override for the bar fill color (e.g. accent terracotta for margin view). */
  barColor?: string;
  formatValue?: (valueMicros: number) => string;
}

export function BreakdownCard({ title, items, barColor, formatValue }: BreakdownCardProps) {
  const fmt = formatValue ?? formatCostMicros;
  const maxPercentage = Math.max(...items.map((i) => i.percentage));

  return (
    <ChartCard title={title}>
      <div>
        {items.map((item, idx) => (
          <div
            key={item.key}
            className={cn(
              "flex items-center gap-3 border-b border-bg-subtle py-2.5",
              "last:border-0",
            )}
          >
            <span
              className="h-2 w-2 shrink-0 rounded-full"
              style={{ backgroundColor: paletteColor(idx) }}
            />
            <span className="flex-1 text-[13px]">{item.label}</span>
            <span className="min-w-[65px] text-right font-mono text-[13px] font-semibold">
              {fmt(item.valueMicros)}
            </span>
            <div className="h-[5px] w-[72px] overflow-hidden rounded-full bg-bg-subtle">
              <div
                className="h-full rounded-full"
                style={{
                  width: `${(item.percentage / maxPercentage) * 100}%`,
                  backgroundColor: barColor ?? paletteColor(idx),
                }}
              />
            </div>
            <span className="min-w-[34px] text-right text-[11px] font-medium text-text-muted">
              {item.percentage}%
            </span>
          </div>
        ))}
      </div>
    </ChartCard>
  );
}
