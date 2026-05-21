// src/features/export/api/types.ts

export type ExportGranularity = "dimension" | "event";
export type ExportFormat = "csv" | "json";
export type DatePreset = "7d" | "30d" | "90d" | "all";

export interface ExportFilters {
  dateFrom: string; // "YYYY-MM-DD"
  dateTo: string; // "YYYY-MM-DD"
  customerIds: string[]; // empty = all
  productKeys: string[]; // empty = all
  cardKeys: string[]; // empty = all
  granularity: ExportGranularity;
}

export interface ExportEstimate {
  rowCount: number;
  fileSizeBytes: number;
}

export interface PreviewColumn {
  key: string;
  label: string;
  align?: "left" | "right";
  bold?: boolean; // render non-null values in font-medium
  muted?: boolean; // render all values in muted color (e.g., dimension name column)
}

export interface ExportPreviewData {
  estimate: ExportEstimate;
  columns: PreviewColumn[];
  rows: Record<string, string | number | null>[];
}

export interface FilterOptionCustomer {
  id: string;
  name: string;
  eventCount: number;
}

export interface FilterOptionProduct {
  key: string;
  label: string;
  percentage: number;
}

export interface FilterOptionCard {
  key: string;
  label: string;
  percentage: number;
}

export interface ExportFilterOptions {
  customers: FilterOptionCustomer[];
  products: FilterOptionProduct[];
  cards: FilterOptionCard[];
}
