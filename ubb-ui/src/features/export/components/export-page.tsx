import { useState, useMemo, useEffect, useCallback, useRef } from "react";
import { cn } from "@/lib/utils";
import { PageHeader } from "@/components/shared/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { useExportFilterOptions, useExportPreview, useGenerateExport } from "../api/queries";
import type { DatePreset, ExportFilters, ExportFormat, ExportGranularity } from "../api/types";
import { ExportFilters as ExportFiltersPanel } from "./export-filters";
import { ExportEstimate } from "./export-estimate";
import { DataPreviewTable } from "./data-preview-table";

function getPresetDates(preset: DatePreset): { from: string; to: string } {
  const to = new Date();
  const toStr = to.toISOString().split("T")[0]!;
  if (preset === "all") return { from: "2026-01-12", to: toStr };
  const days = preset === "7d" ? 7 : preset === "30d" ? 30 : 90;
  const from = new Date(to);
  from.setDate(from.getDate() - days);
  return { from: from.toISOString().split("T")[0]!, to: toStr };
}

function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  const serialized = JSON.stringify(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serialized, delayMs]);
  return debounced;
}

export function ExportPage() {
  const { data: filterOptions, isLoading: optionsLoading } =
    useExportFilterOptions();

  const defaultDates = getPresetDates("30d");
  const [dateFrom, setDateFrom] = useState(defaultDates.from);
  const [dateTo, setDateTo] = useState(defaultDates.to);
  const [datePreset, setDatePreset] = useState<DatePreset | null>("30d");
  const [selectedCustomerIds, setSelectedCustomerIds] = useState<string[]>([]);
  const [selectedProductKeys, setSelectedProductKeys] = useState<string[]>([]);
  const [selectedCardKeys, setSelectedCardKeys] = useState<string[]>([]);
  const [granularity, setGranularity] = useState<ExportGranularity>("dimension");
  const [format, setFormat] = useState<ExportFormat>("csv");

  const filters = useMemo<ExportFilters>(
    () => ({
      dateFrom,
      dateTo,
      customerIds: selectedCustomerIds,
      productKeys: selectedProductKeys,
      cardKeys: selectedCardKeys,
      granularity,
    }),
    [dateFrom, dateTo, selectedCustomerIds, selectedProductKeys, selectedCardKeys, granularity],
  );

  const debouncedFilters = useDebouncedValue(filters, 300);
  const { data: preview } = useExportPreview(
    filterOptions ? debouncedFilters : null,
  );
  const exportMutation = useGenerateExport();

  const handleDatePreset = useCallback((preset: DatePreset) => {
    const dates = getPresetDates(preset);
    setDateFrom(dates.from);
    setDateTo(dates.to);
    setDatePreset(preset);
  }, []);

  const handleDateFromChange = useCallback((value: string) => {
    setDateFrom(value);
    setDatePreset(null);
  }, []);

  const handleDateToChange = useCallback((value: string) => {
    setDateTo(value);
    setDatePreset(null);
  }, []);

  const exportMutate = exportMutation.mutate;
  const handleDownload = useCallback(() => {
    exportMutate(filters);
  }, [exportMutate, filters]);

  // Browser download trigger (moved from DownloadBar)
  const triggeredUrlRef = useRef<string | undefined>(undefined);
  const [showReady, setShowReady] = useState(false);

  useEffect(() => {
    if (!exportMutation.isSuccess || !exportMutation.data?.downloadUrl) return;
    const url = exportMutation.data.downloadUrl;
    if (triggeredUrlRef.current === url) return;
    triggeredUrlRef.current = url;

    const a = document.createElement("a");
    a.href = url;
    a.download = "";
    a.rel = "noopener";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);

    const showTimer = setTimeout(() => setShowReady(true), 0);
    const hideTimer = setTimeout(() => setShowReady(false), 2500);
    return () => {
      clearTimeout(showTimer);
      clearTimeout(hideTimer);
    };
  }, [exportMutation.isSuccess, exportMutation.data?.downloadUrl]);

  if (optionsLoading || !filterOptions) {
    return (
      <div className="mx-auto max-w-4xl space-y-4">
        <PageHeader title="Export raw data" />
        <Skeleton className="h-64 rounded-lg" />
        <Skeleton className="h-12 rounded-md" />
        <Skeleton className="h-48 rounded-md" />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <PageHeader
        title="Export raw data"
        description="Download event-level data as a file. Filters narrow your export — the preview and estimate update live as you go."
      />

      <ExportFiltersPanel
        filterOptions={filterOptions}
        dateFrom={dateFrom}
        dateTo={dateTo}
        datePreset={datePreset}
        onDateFromChange={handleDateFromChange}
        onDateToChange={handleDateToChange}
        onDatePreset={handleDatePreset}
        selectedCustomerIds={selectedCustomerIds}
        onCustomerSelectionChange={setSelectedCustomerIds}
        selectedProductKeys={selectedProductKeys}
        onProductSelectionChange={setSelectedProductKeys}
        selectedCardKeys={selectedCardKeys}
        onCardSelectionChange={setSelectedCardKeys}
        format={format}
        onFormatChange={setFormat}
        granularity={granularity}
        onGranularityChange={setGranularity}
      />

      {preview && (
        <>
          <ExportEstimate
            estimate={preview.estimate}
            filterOptions={filterOptions}
            selectedCustomerIds={selectedCustomerIds}
            selectedProductKeys={selectedProductKeys}
            selectedCardKeys={selectedCardKeys}
            dateFrom={dateFrom}
            dateTo={dateTo}
            downloadButton={
              <button
                className={cn(
                  "inline-flex items-center gap-2 rounded-full px-5 py-2 text-[13px] font-medium text-text-inverse",
                  showReady
                    ? "bg-green"
                    : "bg-accent-base hover:bg-accent-hover",
                  exportMutation.isPending && "opacity-60",
                )}
                onClick={handleDownload}
                disabled={exportMutation.isPending}
              >
                <svg width="13" height="13" viewBox="0 0 13 13" fill="none">
                  <path d="M6.5 1v8M3.5 6l3 3 3-3M1.5 11.5h10" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/>
                </svg>
                {exportMutation.isPending
                  ? "Generating..."
                  : showReady
                    ? "Download ready"
                    : `Download ${format.toUpperCase()}`}
              </button>
            }
          />

          <DataPreviewTable
            columns={preview.columns}
            rows={preview.rows}
            totalRowCount={preview.estimate.rowCount}
          />
        </>
      )}
    </div>
  );
}
