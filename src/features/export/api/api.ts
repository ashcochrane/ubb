// src/features/export/api/api.ts
import type {
  ExportFilterOptions,
  ExportFilters,
  ExportPreviewData,
} from "./types";
import { platformApi } from "@/api/client";

export async function getFilterOptions(): Promise<ExportFilterOptions> {
  const { data } = await platformApi.GET("/export/filter-options", {});
  return data as ExportFilterOptions;
}

export async function getPreview(
  filters: ExportFilters,
): Promise<ExportPreviewData> {
  const { data } = await platformApi.POST("/export/preview", {
    body: filters,
  });
  return data as ExportPreviewData;
}

export async function generateExport(
  filters: ExportFilters,
): Promise<{ downloadUrl: string }> {
  const { data } = await platformApi.POST("/export/generate", {
    body: filters,
  });
  return data as { downloadUrl: string };
}
