import { Download } from "lucide-react";
import { cn } from "@/lib/utils";
import type { TimeRange } from "../api/types";

interface ScopeBarProps {
  timeRange: TimeRange;
  onTimeRangeChange: (range: TimeRange) => void;
  onExport?: () => void;
}

type ScopeKey = "all" | "top5" | "unprofitable";

const SCOPE_TABS: { key: ScopeKey; label: string }[] = [
  { key: "all",           label: "All customers" },
  { key: "top5",          label: "Top 5 by revenue" },
  { key: "unprofitable",  label: "Unprofitable" },
];

const RANGE_OPTIONS: { value: TimeRange; label: string }[] = [
  { value: "7d",  label: "7d" },
  { value: "30d", label: "30d" },
  { value: "90d", label: "90d" },
  { value: "YTD", label: "YTD" },
];

const RANGE_CONTEXT: Record<TimeRange, string> = {
  "7d":  "7-day period",
  "30d": "30-day period",
  "90d": "90-day period",
  "YTD": "Year-to-date",
};

export function ScopeBar({ timeRange, onTimeRangeChange, onExport }: ScopeBarProps) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2.5">
      <div className="flex items-center gap-3.5">
        <ScopePillTabs activeKey="all" />
        <span className="text-[11px] text-text-muted">
          Showing: <b className="font-semibold text-text-secondary">All 18 customers</b> (aggregate)
        </span>
      </div>

      <div className="flex items-center gap-2.5">
        <span className="text-[11px] text-text-muted">{RANGE_CONTEXT[timeRange]}</span>
        <DayRangePillGroup value={timeRange} onChange={onTimeRangeChange} />
        <button
          type="button"
          onClick={onExport}
          disabled={!onExport}
          className="inline-flex items-center gap-1.5 rounded-full border border-border-mid bg-bg-surface px-3 py-[5px] text-[11px] font-medium text-text-secondary transition-colors hover:bg-bg-subtle hover:text-text-primary disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:bg-bg-surface disabled:hover:text-text-secondary"
        >
          <Download className="h-[11px] w-[11px]" />
          Export
        </button>
      </div>
    </div>
  );
}

// Display-only for now — no state machine wired through. When the backend
// supports scope filters, add `scope` + `onScopeChange` to `ScopeBarProps`
// and thread through to the buttons.
function ScopePillTabs({ activeKey }: { activeKey: ScopeKey }) {
  return (
    <div
      role="tablist"
      className="flex gap-px rounded-full border border-border bg-bg-surface p-[3px]"
    >
      {SCOPE_TABS.map((tab) => {
        const isActive = tab.key === activeKey;
        return (
          <button
            key={tab.key}
            type="button"
            role="tab"
            aria-selected={isActive}
            aria-disabled={!isActive}
            tabIndex={isActive ? 0 : -1}
            className={cn(
              "rounded-full px-3 py-1 text-[11px] transition-colors",
              isActive
                ? "bg-accent-ghost font-semibold text-accent-text"
                : "cursor-not-allowed text-text-muted",
            )}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}

function DayRangePillGroup({
  value,
  onChange,
}: {
  value: TimeRange;
  onChange: (range: TimeRange) => void;
}) {
  return (
    <div className="flex gap-px rounded-full bg-bg-subtle p-[2px]">
      {RANGE_OPTIONS.map((opt) => (
        <button
          key={opt.value}
          type="button"
          onClick={() => onChange(opt.value)}
          className={cn(
            "rounded-full px-2.5 py-[3px] text-[10px] font-medium transition-colors",
            value === opt.value
              ? "bg-bg-surface text-text-primary shadow-sm"
              : "text-text-muted hover:text-text-secondary",
          )}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
