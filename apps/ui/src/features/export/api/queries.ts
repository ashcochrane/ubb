// src/features/export/api/queries.ts
import { useMutation, useQuery } from "@tanstack/react-query";
import { toastOnError } from "@/lib/mutations";
import { exportApi } from "./provider";
import type { ExportFilters } from "./types";

export function useExportFilterOptions() {
  return useQuery({
    queryKey: ["export-filter-options"],
    queryFn: () => exportApi.getFilterOptions(),
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

export function useExportPreview(filters: ExportFilters | null) {
  return useQuery({
    queryKey: ["export-preview", filters],
    queryFn: () => exportApi.getPreview(filters!),
    enabled: filters !== null,
    placeholderData: (prev) => prev, // keep previous data while refetching
  });
}

export function useGenerateExport() {
  return useMutation({
    mutationFn: (filters: ExportFilters) => exportApi.generateExport(filters),
    onError: toastOnError("Couldn't generate export"),
  });
}
