import type { MarginSchemas } from "@/api/types";

// Analytical snapshots (whole-period; NOT cursor-paginated).
export type MarginSummary = MarginSchemas["MarginSummaryOut"];
export type MarginList = MarginSchemas["MarginListOut"];
export type CustomerMarginRow = MarginSchemas["CustomerMarginListRow"];
export type MarginByDimension = MarginSchemas["MarginByDimensionOut"];
export type DimensionMarginRow = MarginSchemas["DimensionMarginRow"];
export type Unprofitable = MarginSchemas["UnprofitableOut"];
export type UnprofitableCustomerRow = MarginSchemas["UnprofitableCustomerRow"];

// Threshold config (unprofitability alerts).
export type MarginThreshold = MarginSchemas["MarginThresholdOut"];
export type MarginThresholdInput = MarginSchemas["MarginThresholdIn"];

// Per-business drill-down.
export type BusinessMargin = MarginSchemas["BusinessMarginOut"];
export type SeatMargin = MarginSchemas["SeatMarginOut"];

/** Shared start/end date window applied to the analytical tabs. */
export interface DateRange {
  start_date: string;
  end_date: string;
}

/** Filters for the by-dimension breakdown. */
export interface DimensionFilters {
  provider?: number;
  product?: number;
  tag_key?: string;
}
