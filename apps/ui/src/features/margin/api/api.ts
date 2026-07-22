import { marginApi } from "@/api/client";
import { requireData } from "@/api/errors";
import type {
  BusinessMargin,
  DateRange,
  DimensionFilters,
  MarginByDimension,
  MarginList,
  MarginSummary,
  MarginThreshold,
  MarginThresholdInput,
  Unprofitable,
} from "./types";

export function getSummary(range: DateRange): Promise<MarginSummary> {
  return marginApi
    .GET("/summary", { params: { query: range } })
    .then((r) => requireData(r, "Failed to load margin summary"));
}

export function getCustomers(range: DateRange): Promise<MarginList> {
  return marginApi
    .GET("/customers", { params: { query: range } })
    .then((r) => requireData(r, "Failed to load customer margins"));
}

export function getByDimension(
  range: DateRange,
  filters: DimensionFilters,
): Promise<MarginByDimension> {
  return marginApi
    .GET("/by-dimension", { params: { query: { ...range, ...filters } } })
    .then((r) => requireData(r, "Failed to load margin by dimension"));
}

export function getUnprofitable(periodStart?: string): Promise<Unprofitable> {
  return marginApi
    .GET("/unprofitable", {
      params: { query: periodStart ? { period_start: periodStart } : {} },
    })
    .then((r) => requireData(r, "Failed to load unprofitable customers"));
}

export function getThreshold(): Promise<MarginThreshold> {
  return marginApi
    .GET("/threshold")
    .then((r) => requireData(r, "Failed to load margin threshold"));
}

export function putThreshold(
  body: MarginThresholdInput,
): Promise<MarginThreshold> {
  return marginApi
    .PUT("/threshold", { body })
    .then((r) => requireData(r, "Failed to save margin threshold"));
}

export function getBusinessMargin(externalId: string): Promise<BusinessMargin> {
  return marginApi
    .GET("/business/{external_id}", {
      params: { path: { external_id: externalId } },
    })
    .then((r) => requireData(r, "Failed to load business margin"));
}
