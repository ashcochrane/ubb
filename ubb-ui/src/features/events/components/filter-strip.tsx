import { useCallback, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import { ChevronDown } from "lucide-react";
import type { EventFilterOptions, EventFilters } from "../api/types";
import { FilterPopover } from "./filter-popover";
import { DatePopover } from "./date-popover";

type DatePreset = "7d" | "30d" | "90d" | "all";

interface FilterStripProps {
  filterOptions: EventFilterOptions;
  filters: EventFilters;
  onFiltersChange: (f: EventFilters) => void;
  datePreset: DatePreset | null;
  onDatePresetChange: (p: DatePreset | null) => void;
}

type OpenPopover = "date" | "cust" | "grp" | "card" | null;

function formatDateRange(from: string, to: string): string {
  const fmt = (d: string) => {
    const dt = new Date(d + "T00:00:00");
    return dt.toLocaleDateString("en-GB", { day: "numeric", month: "short" });
  };
  return `${fmt(from)} \u2014 ${fmt(to)}`;
}

export function FilterStrip({
  filterOptions,
  filters,
  onFiltersChange,
  datePreset,
  onDatePresetChange,
}: FilterStripProps) {
  const [openPop, setOpenPop] = useState<OpenPopover>(null);
  const [anchorRect, setAnchorRect] = useState<DOMRect | null>(null);
  const containerRef = useRef<HTMLDivElement>(null);

  const openPopover = useCallback((type: OpenPopover, el: HTMLElement) => {
    const containerRect = containerRef.current?.getBoundingClientRect();
    const elRect = el.getBoundingClientRect();
    if (containerRect) {
      setAnchorRect(new DOMRect(
        elRect.left - containerRect.left,
        elRect.bottom - containerRect.top,
        elRect.width,
        0,
      ));
    }
    setOpenPop(type);
  }, []);

  const closePopover = useCallback(() => {
    setOpenPop(null);
    setAnchorRect(null);
  }, []);

  const hasAnyFilter = filters.customerKey || filters.groupKey || filters.cardKey;

  function clearAll() {
    onFiltersChange({ ...filters, customerKey: "", groupKey: "", cardKey: "" });
  }

  const pillBase =
    "flex cursor-pointer items-center gap-1.5 rounded-full border bg-bg-surface px-3 py-1.5 transition-colors hover:bg-bg-subtle";

  return (
    <div ref={containerRef} className="relative flex flex-wrap items-center gap-1.5">
      {/* Date range */}
      <button
        className={cn(
          pillBase,
          datePreset ? "border-accent-border" : "border-border-mid",
        )}
        onClick={(e) => openPopover("date", e.currentTarget)}
      >
        <div className="leading-tight">
          <div className="text-[9px] font-bold uppercase tracking-[0.06em] text-text-muted">Date range</div>
          <div className="font-mono text-[11px] text-text-primary">
            {formatDateRange(filters.dateFrom, filters.dateTo)}
          </div>
        </div>
        <ChevronDown className="h-2.5 w-2.5 text-text-muted" />
      </button>

      <div className="mx-0.5 h-[22px] w-px shrink-0 bg-border" />

      {/* Customer */}
      <button
        className={cn(
          pillBase,
          filters.customerKey ? "border-accent-border" : "border-border-mid",
        )}
        onClick={(e) => openPopover("cust", e.currentTarget)}
      >
        <div className="leading-tight">
          <div className="text-[9px] font-bold uppercase tracking-[0.06em] text-text-muted">Customer</div>
          <div className={cn("text-[11px]", filters.customerKey ? "font-medium text-accent-text" : "text-text-secondary")}>
            {filters.customerKey || "All customers"}
          </div>
        </div>
        <ChevronDown className="h-2.5 w-2.5 text-text-muted" />
      </button>

      {/* Group */}
      <button
        className={cn(
          pillBase,
          filters.groupKey ? "border-accent-border" : "border-border-mid",
        )}
        onClick={(e) => openPopover("grp", e.currentTarget)}
      >
        <div className="leading-tight">
          <div className="text-[9px] font-bold uppercase tracking-[0.06em] text-text-muted">Group</div>
          <div className={cn("text-[11px]", filters.groupKey ? "font-medium text-accent-text" : "text-text-secondary")}>
            {filters.groupKey === "(ungrouped)"
              ? `Ungrouped (${filterOptions.ungroupedCount})`
              : filters.groupKey || "All groups"}
          </div>
        </div>
        <ChevronDown className="h-2.5 w-2.5 text-text-muted" />
      </button>

      {/* Card */}
      <button
        className={cn(
          pillBase,
          filters.cardKey ? "border-accent-border" : "border-border-mid",
        )}
        onClick={(e) => openPopover("card", e.currentTarget)}
      >
        <div className="leading-tight">
          <div className="text-[9px] font-bold uppercase tracking-[0.06em] text-text-muted">Pricing card</div>
          <div className={cn("text-[11px]", filters.cardKey ? "font-medium text-accent-text" : "text-text-secondary")}>
            {filters.cardKey || "All cards"}
          </div>
        </div>
        <ChevronDown className="h-2.5 w-2.5 text-text-muted" />
      </button>

      <div className="mx-0.5 h-[22px] w-px shrink-0 bg-border" />

      {/* Ungrouped chip */}
      {filterOptions.ungroupedCount > 0 && (
        <button
          className="rounded-full border border-amber-border bg-amber-light px-3 py-1.5 text-[10px] font-medium text-amber-text"
          onClick={() => onFiltersChange({ ...filters, groupKey: "(ungrouped)" })}
        >
          {filterOptions.ungroupedCount} ungrouped
        </button>
      )}

      {/* Clear all */}
      {hasAnyFilter && (
        <button
          className="rounded-full border border-border-mid px-3 py-1.5 text-[10px] text-text-muted hover:bg-bg-subtle hover:text-text-secondary"
          onClick={clearAll}
        >
          Clear all
        </button>
      )}

      {/* Popovers */}
      {openPop === "date" && (
        <DatePopover
          dateFrom={filters.dateFrom}
          dateTo={filters.dateTo}
          activePreset={datePreset}
          onApply={(from, to, preset) => {
            onFiltersChange({ ...filters, dateFrom: from, dateTo: to });
            onDatePresetChange(preset);
            closePopover();
          }}
          onClose={closePopover}
          anchorRect={anchorRect}
        />
      )}
      {openPop === "cust" && (
        <FilterPopover
          items={filterOptions.customers}
          selected={filters.customerKey}
          allLabel="All customers"
          onPick={(k) => { onFiltersChange({ ...filters, customerKey: k }); closePopover(); }}
          onClose={closePopover}
          anchorRect={anchorRect}
        />
      )}
      {openPop === "grp" && (
        <FilterPopover
          items={[
            { key: "(ungrouped)", eventCount: filterOptions.ungroupedCount },
            ...filterOptions.groups,
          ]}
          selected={filters.groupKey}
          allLabel="All groups"
          onPick={(k) => { onFiltersChange({ ...filters, groupKey: k }); closePopover(); }}
          onClose={closePopover}
          anchorRect={anchorRect}
        />
      )}
      {openPop === "card" && (
        <FilterPopover
          items={filterOptions.cards}
          selected={filters.cardKey}
          allLabel="All cards"
          onPick={(k) => { onFiltersChange({ ...filters, cardKey: k }); closePopover(); }}
          onClose={closePopover}
          anchorRect={anchorRect}
        />
      )}
    </div>
  );
}
