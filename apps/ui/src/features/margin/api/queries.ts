import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { toastOnError } from "@/lib/mutations";
import * as api from "./api";
import type {
  DateRange,
  DimensionFilters,
  MarginThresholdInput,
} from "./types";

const KEY = "margin";
const rangeKey = (r: DateRange) => [r.start_date, r.end_date] as const;

export const useMarginSummary = (range: DateRange) =>
  useQuery({
    queryKey: [KEY, "summary", ...rangeKey(range)],
    queryFn: () => api.getSummary(range),
  });

export const useMarginCustomers = (range: DateRange) =>
  useQuery({
    queryKey: [KEY, "customers", ...rangeKey(range)],
    queryFn: () => api.getCustomers(range),
  });

export const useMarginByDimension = (
  range: DateRange,
  filters: DimensionFilters,
) =>
  useQuery({
    queryKey: [KEY, "by-dimension", ...rangeKey(range), filters],
    queryFn: () => api.getByDimension(range, filters),
  });

export const useUnprofitable = (periodStart?: string) =>
  useQuery({
    queryKey: [KEY, "unprofitable", periodStart ?? null],
    queryFn: () => api.getUnprofitable(periodStart),
  });

export const useMarginThreshold = () =>
  useQuery({
    queryKey: [KEY, "threshold"],
    queryFn: () => api.getThreshold(),
  });

export function useSaveThreshold() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: MarginThresholdInput) => api.putThreshold(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: [KEY, "threshold"] });
      qc.invalidateQueries({ queryKey: [KEY, "unprofitable"] });
      toast.success("Margin threshold saved");
    },
    onError: toastOnError("Couldn't save margin threshold"),
  });
}

/** Manual lookup — only fires once an external id is submitted. */
export const useBusinessMargin = (externalId: string) =>
  useQuery({
    queryKey: [KEY, "business", externalId],
    queryFn: () => api.getBusinessMargin(externalId),
    enabled: !!externalId,
  });
