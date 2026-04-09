// src/features/dashboard/components/scope-bar.tsx
import { cn } from "@/lib/utils";
import { Download } from "lucide-react";
import type { TimeRange } from "../api/types";

interface ScopeBarProps {
  timeRange: TimeRange;
  onTimeRangeChange: (range: TimeRange) => void;
}

const timeRanges: { value: TimeRange; label: string }[] = [
  { value: "7d", label: "7d" },
  { value: "30d", label: "30d" },
  { value: "90d", label: "90d" },
  { value: "YTD", label: "YTD" },
];

export function ScopeBar({ timeRange, onTimeRangeChange }: ScopeBarProps) {
  return (
    <div className="space-y-3">
      {/* Scope presets */}
      <div className="flex items-center gap-1.5 rounded-xl bg-accent/50 px-3.5 py-2.5">
        <ScopeButton label="All customers" selected />
        <div className="mx-1 h-5 w-px bg-border" />
        <ScopeButton label="Top 5 by revenue" query />
        <ScopeButton label="Unprofitable" query />
      </div>

      {/* View label + controls */}
      <div className="flex items-center justify-between">
        <div>
          <span className="text-[12px] font-medium">Showing: All 18 customers</span>
          <span className="ml-1 text-[12px] text-muted-foreground">(aggregate)</span>
        </div>
        <span className="text-[11px] text-muted-foreground">30-day period</span>
      </div>

      {/* Time range + export */}
      <div className="flex items-center justify-between">
        <div className="flex overflow-hidden rounded-lg border border-border">
          {timeRanges.map((tr) => (
            <button
              key={tr.value}
              type="button"
              onClick={() => onTimeRangeChange(tr.value)}
              className={cn(
                "px-3 py-1 text-[11px] transition-colors",
                timeRange === tr.value
                  ? "bg-foreground text-background"
                  : "text-muted-foreground hover:bg-accent",
              )}
            >
              {tr.label}
            </button>
          ))}
        </div>
        <button className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1 text-[11px] text-muted-foreground hover:bg-accent">
          <Download className="h-3 w-3" /> Export
        </button>
      </div>
    </div>
  );
}

function ScopeButton({ label, selected, query }: { label: string; selected?: boolean; query?: boolean }) {
  return (
    <button
      type="button"
      className={cn(
        "rounded-full px-3.5 py-1 text-[11px] transition-colors",
        selected && "bg-foreground text-background",
        !selected && !query && "border border-border text-muted-foreground hover:border-muted-foreground",
        !selected && query && "border border-dashed border-border text-muted-foreground hover:border-muted-foreground",
      )}
    >
      {label}
    </button>
  );
}
