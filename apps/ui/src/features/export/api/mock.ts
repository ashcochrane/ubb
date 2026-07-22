// src/features/export/api/mock.ts
import type {
  ExportFilterOptions,
  ExportFilters,
  ExportPreviewData,
} from "./types";
import {
  mockFilterOptions,
  dimensionColumns,
  dimensionRows,
  eventColumns,
  eventRows,
  productPcts,
  cardPcts,
} from "./mock-data";
import { mockDelay } from "@/lib/api-provider";

export async function getFilterOptions(): Promise<ExportFilterOptions> {
  await mockDelay();
  return structuredClone(mockFilterOptions);
}

function computeEstimate(filters: ExportFilters) {
  const from = new Date(filters.dateFrom);
  const to = new Date(filters.dateTo);
  const days = Math.max(1, Math.round((to.getTime() - from.getTime()) / 86_400_000));

  let rows = 8_260 * days;

  if (filters.customerIds.length > 0) {
    rows = Math.round(rows * (filters.customerIds.length / mockFilterOptions.customers.length));
  }
  if (filters.productKeys.length > 0) {
    const frac = filters.productKeys.reduce((s, k) => s + (productPcts[k] ?? 0), 0);
    rows = Math.round(rows * frac);
  }
  if (filters.cardKeys.length > 0) {
    const frac = filters.cardKeys.reduce((s, k) => s + (cardPcts[k] ?? 0), 0);
    rows = Math.round(rows * frac);
  }
  if (filters.granularity === "event") {
    rows = Math.round(rows / 2.8);
  }

  rows = Math.max(0, rows);
  const fileSizeBytes = Math.round(Math.max(100, rows * 75));

  return { rowCount: rows, fileSizeBytes };
}

export async function getPreview(
  filters: ExportFilters,
): Promise<ExportPreviewData> {
  await mockDelay();
  const estimate = computeEstimate(filters);
  const columns = filters.granularity === "event" ? eventColumns : dimensionColumns;
  const rows = filters.granularity === "event" ? eventRows : dimensionRows;
  return {
    estimate,
    columns: structuredClone(columns),
    rows: structuredClone(rows),
  };
}

export async function generateExport(
  filters: ExportFilters,
): Promise<{ downloadUrl: string }> {
  await mockDelay(1500);
  // Mock ignores filters today; reference to silence unused-arg lint.
  void filters;
  return { downloadUrl: "#mock-download" };
}
