// src/features/dashboard/components/breakdown-card.tsx
import type { ProductBreakdown } from "../api/types";

interface BreakdownCardProps {
  title: string;
  items: ProductBreakdown[];
  /** Override bar fill color (e.g. teal for margin bars). Defaults to item.color. */
  barColor?: string;
  formatValue?: (value: number) => string;
}

export function BreakdownCard({ title, items, barColor, formatValue }: BreakdownCardProps) {
  const fmt = formatValue ?? ((v: number) => `$${v.toLocaleString()}`);
  const maxPercentage = Math.max(...items.map((i) => i.percentage));

  return (
    <div className="rounded-xl border border-border px-4 py-3.5">
      <div className="mb-3 text-[13px] font-semibold">{title}</div>
      <div className="space-y-2.5">
        {items.map((item) => (
          <div key={item.key} className="flex items-center gap-2.5 border-b border-border/50 pb-2 last:border-0 last:pb-0">
            <div
              className="h-2 w-2 shrink-0 rounded-sm"
              style={{ backgroundColor: item.color }}
            />
            <span className="flex-1 text-[12px] text-muted-foreground">{item.label}</span>
            <div className="w-11">
              <div className="h-1 rounded-full bg-muted">
                <div
                  className="h-1 rounded-full"
                  style={{
                    width: `${(item.percentage / maxPercentage) * 100}%`,
                    backgroundColor: barColor ?? item.color,
                  }}
                />
              </div>
            </div>
            <span className="w-14 text-right font-mono text-[11px] font-semibold">{fmt(item.value)}</span>
            <span className="w-10 text-right font-mono text-[10px] text-muted-foreground">
              {item.percentage}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
