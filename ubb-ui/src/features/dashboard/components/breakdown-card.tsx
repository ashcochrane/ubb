import { ChartCard } from "@/components/shared/chart-card";
import { cn } from "@/lib/utils";
import type { ProductBreakdown } from "../api/types";

interface BreakdownCardProps {
  title: string;
  items: ProductBreakdown[];
  /** Optional override for the bar fill color (e.g. accent terracotta for margin view). */
  barColor?: string;
  formatValue?: (value: number) => string;
}

export function BreakdownCard({ title, items, barColor, formatValue }: BreakdownCardProps) {
  const fmt = formatValue ?? ((v: number) => `$${v.toLocaleString()}`);
  const maxPercentage = Math.max(...items.map((i) => i.percentage));

  return (
    <ChartCard title={title}>
      <div>
        {items.map((item) => (
          <div
            key={item.key}
            className={cn(
              "flex items-center gap-3 border-b border-bg-subtle py-2.5",
              "last:border-0",
            )}
          >
            <span
              className="h-2 w-2 shrink-0 rounded-full"
              style={{ backgroundColor: item.color }}
            />
            <span className="flex-1 text-[13px]">{item.label}</span>
            <span className="min-w-[65px] text-right font-mono text-[13px] font-semibold">
              {fmt(item.value)}
            </span>
            <div className="h-[5px] w-[72px] overflow-hidden rounded-full bg-bg-subtle">
              <div
                className="h-full rounded-full"
                style={{
                  width: `${(item.percentage / maxPercentage) * 100}%`,
                  backgroundColor: barColor ?? item.color,
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
