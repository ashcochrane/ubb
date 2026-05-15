// src/features/export/components/export-estimate.tsx
import { memo } from "react";
import { AlertCircle } from "lucide-react";
import { formatFileSize } from "@/lib/format";
import type { ExportEstimate as EstimateData, ExportFilterOptions } from "../api/types";

function formatDayMonth(isoDate: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
  }).format(new Date(isoDate + "T00:00:00Z"));
}

function formatDayMonthYear(isoDate: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    day: "numeric",
    month: "short",
    year: "numeric",
  }).format(new Date(isoDate + "T00:00:00Z"));
}

interface ExportEstimateProps {
  estimate: EstimateData;
  filterOptions: ExportFilterOptions;
  selectedCustomerIds: string[];
  selectedProductKeys: string[];
  selectedCardKeys: string[];
  dateFrom: string;
  dateTo: string;
  downloadButton?: React.ReactNode;
}

function ExportEstimateImpl({
  estimate,
  filterOptions,
  selectedCustomerIds,
  selectedProductKeys,
  selectedCardKeys,
  dateFrom,
  dateTo,
  downloadButton,
}: ExportEstimateProps) {
  const customerText =
    selectedCustomerIds.length === 0
      ? `all ${filterOptions.customers.length} customers`
      : selectedCustomerIds.length === 1
        ? (filterOptions.customers.find((c) => c.id === selectedCustomerIds[0])?.name ?? "1 customer")
        : `${selectedCustomerIds.length} customers`;

  const productText =
    selectedProductKeys.length === 0
      ? "all products"
      : selectedProductKeys
          .map((k) => filterOptions.products.find((p) => p.key === k)?.label)
          .filter(Boolean)
          .join(", ");

  const cardText =
    selectedCardKeys.length === 0
      ? "all pricing cards"
      : selectedCardKeys
          .map((k) => filterOptions.cards.find((c) => c.key === k)?.label)
          .filter(Boolean)
          .join(", ");

  const days = Math.max(
    1,
    Math.round(
      (new Date(dateTo).getTime() - new Date(dateFrom).getTime()) / 86_400_000,
    ),
  );

  const dateRange = `${formatDayMonth(dateFrom)} \u2014 ${formatDayMonthYear(dateTo)}`;

  return (
    <div>
      <div className="flex items-center justify-between py-3.5">
        <p className="flex-1 text-[13px] leading-relaxed text-text-secondary">
          Exporting <strong className="text-text-primary">all events</strong>{" "}
          across{" "}
          <strong className="text-text-primary">{customerText}</strong>,{" "}
          <strong className="text-text-primary">{productText}</strong>, and{" "}
          <strong className="text-text-primary">{cardText}</strong> from{" "}
          <strong className="text-text-primary">{dateRange}</strong>{" "}
          <span className="text-text-muted">({days} day{days !== 1 && "s"})</span>.
        </p>
        <div className="flex items-center">
          <div className="flex gap-6">
            <div className="text-right">
              <div className="text-[22px] font-bold tracking-[-0.5px] text-accent-text">
                {estimate.rowCount.toLocaleString()}
              </div>
              <div className="mt-0.5 text-[10px] font-bold uppercase tracking-[0.06em] text-text-muted">rows</div>
            </div>
            <div className="text-right">
              <div className="text-[22px] font-bold tracking-[-0.5px] text-accent-text">
                {formatFileSize(estimate.fileSizeBytes)}
              </div>
              <div className="mt-0.5 text-[10px] font-bold uppercase tracking-[0.06em] text-text-muted">file size</div>
            </div>
          </div>
          {downloadButton && <div className="ml-6">{downloadButton}</div>}
        </div>
      </div>
      {estimate.rowCount > 500_000 && (
        <div className="flex items-center gap-2 rounded-lg bg-amber-light px-2.5 py-1.5 text-label text-amber-text">
          <AlertCircle className="h-3.5 w-3.5 shrink-0" />
          Large export — consider adding filters to reduce the file size.
        </div>
      )}
    </div>
  );
}

export const ExportEstimate = memo(ExportEstimateImpl);
