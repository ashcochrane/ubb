import { memo } from "react";
import { cn } from "@/lib/utils";
import type {
  DatePreset,
  ExportFilterOptions,
  ExportFormat,
  ExportGranularity,
} from "../api/types";
import { CustomerMultiSelect } from "./customer-multi-select";
import { TogglePillGroup } from "./toggle-pill-group";

interface ExportFiltersProps {
  filterOptions: ExportFilterOptions;
  dateFrom: string;
  dateTo: string;
  datePreset: DatePreset | null;
  onDateFromChange: (v: string) => void;
  onDateToChange: (v: string) => void;
  onDatePreset: (preset: DatePreset) => void;
  selectedCustomerIds: string[];
  onCustomerSelectionChange: (ids: string[]) => void;
  selectedProductKeys: string[];
  onProductSelectionChange: (keys: string[]) => void;
  selectedCardKeys: string[];
  onCardSelectionChange: (keys: string[]) => void;
  format: ExportFormat;
  onFormatChange: (f: ExportFormat) => void;
  granularity: ExportGranularity;
  onGranularityChange: (g: ExportGranularity) => void;
}

const presets: { key: DatePreset; label: string }[] = [
  { key: "7d", label: "Last 7 days" },
  { key: "30d", label: "Last 30 days" },
  { key: "90d", label: "Last 90 days" },
  { key: "all", label: "All time" },
];

function SegmentedToggle<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: { key: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div>
      <div className="mb-1.5 text-[12px] font-semibold text-text-primary">{label}</div>
      <div className="flex">
        {options.map((opt, i) => (
          <button
            key={opt.key}
            className={cn(
              "border px-3 py-1.5 text-[12px] font-medium",
              i === 0 && "rounded-l-md",
              i === options.length - 1 && "rounded-r-md border-l-0",
              i > 0 && i < options.length - 1 && "border-l-0",
              value === opt.key
                ? "border-accent-base bg-accent-base text-text-inverse"
                : "border-border-mid text-text-secondary hover:bg-bg-subtle",
            )}
            onClick={() => onChange(opt.key)}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function ExportFiltersImpl({
  filterOptions,
  dateFrom,
  dateTo,
  datePreset,
  onDateFromChange,
  onDateToChange,
  onDatePreset,
  selectedCustomerIds,
  onCustomerSelectionChange,
  selectedProductKeys,
  onProductSelectionChange,
  selectedCardKeys,
  onCardSelectionChange,
  format,
  onFormatChange,
  granularity,
  onGranularityChange,
}: ExportFiltersProps) {
  return (
    <div className="rounded-lg border border-border bg-bg-surface px-5 py-5">
      <h2 className="mb-3.5 text-[11px] font-bold uppercase tracking-[0.07em] text-text-muted">Filters</h2>

      <div className="grid max-w-md grid-cols-2 gap-2.5">
        <div>
          <label className="mb-1 block text-[11px] text-text-muted">From</label>
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => onDateFromChange(e.target.value)}
            className="w-full rounded-sm border border-border-mid bg-bg-surface px-3 py-[7px] text-[12px] text-text-primary outline-none focus:border-accent-dark focus:ring-2 focus:ring-accent-base/15"
          />
        </div>
        <div>
          <label className="mb-1 block text-[11px] text-text-muted">To</label>
          <input
            type="date"
            value={dateTo}
            onChange={(e) => onDateToChange(e.target.value)}
            className="w-full rounded-sm border border-border-mid bg-bg-surface px-3 py-[7px] text-[12px] text-text-primary outline-none focus:border-accent-dark focus:ring-2 focus:ring-accent-base/15"
          />
        </div>
      </div>

      <div className="mt-2 flex flex-wrap gap-1.5">
        {presets.map((p) => (
          <button
            key={p.key}
            className={cn(
              "rounded-full border px-3 py-1 text-[12px] font-medium",
              datePreset === p.key
                ? "border-accent-base bg-accent-base text-text-inverse"
                : "border-border-mid bg-bg-surface text-text-secondary hover:bg-bg-subtle hover:text-text-primary",
            )}
            onClick={() => onDatePreset(p.key)}
          >
            {p.label}
          </button>
        ))}
      </div>

      <div className="mt-4 border-t border-border pt-4">
        <CustomerMultiSelect
          customers={filterOptions.customers}
          selectedIds={selectedCustomerIds}
          onSelectionChange={onCustomerSelectionChange}
        />
      </div>

      <div className="mt-4 border-t border-border pt-4">
        <TogglePillGroup
          label="Products"
          allLabel="All products"
          options={filterOptions.products}
          selectedKeys={selectedProductKeys}
          onSelectionChange={onProductSelectionChange}
        />
      </div>

      <div className="mt-4 border-t border-border pt-4">
        <TogglePillGroup
          label="Pricing cards"
          allLabel="All cards"
          options={filterOptions.cards}
          selectedKeys={selectedCardKeys}
          onSelectionChange={onCardSelectionChange}
        />
      </div>

      <div className="mt-4 flex gap-6 border-t border-border pt-4">
        <SegmentedToggle
          label="Format"
          options={[
            { key: "csv" as ExportFormat, label: "CSV" },
            { key: "json" as ExportFormat, label: "JSON" },
          ]}
          value={format}
          onChange={onFormatChange}
        />
        <SegmentedToggle
          label="Granularity"
          options={[
            { key: "dimension" as ExportGranularity, label: "By dimension" },
            { key: "event" as ExportGranularity, label: "By event" },
          ]}
          value={granularity}
          onChange={onGranularityChange}
        />
      </div>
    </div>
  );
}

export const ExportFilters = memo(ExportFiltersImpl);
