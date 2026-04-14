// src/features/dashboard/api/types.ts

export type TimeRange = "7d" | "30d" | "90d" | "YTD";

export interface DailyDataPoint {
  date: string; // "YYYY-MM-DD"
  label: string; // "D Mon" for display
}

export interface RevenueTimeSeries extends DailyDataPoint {
  revenue: number;
  apiCosts: number;
  margin: number;
}

export interface CostByProductPoint extends DailyDataPoint {
  [productKey: string]: number | string; // dynamic product keys + date/label
}

export interface StatsData {
  revenue: number;
  apiCosts: number;
  grossMargin: number;
  marginPercentage: number;
  costPerDollarRevenue: number;
  revenuePrevChange: number;
  costsPrevChange: number;
  marginPrevChange: number;
  marginPctPrevChange: number;
  costPerRevPrevChange: number;
}

export interface ProductBreakdown {
  key: string;
  label: string;
  color: string;
  value: number;
  percentage: number;
}

export interface CustomerRow {
  name: string;
  customerId: string;
  revenue: number;
  revenueType: "Sub" | "Usage";
  apiCosts: number;
  margin: number;
  marginPercentage: number;
  events: number;
}

export interface CostSeries {
  key: string;
  label: string;
  color: string;
}

export interface SparklineSet {
  revenue: number[];
  apiCosts: number[];
  grossMargin: number[];
  marginPct: number[];
  costPerRev: number[];
}

export interface DashboardData {
  stats: StatsData;
  revenueTimeSeries: RevenueTimeSeries[];
  costByProduct: { series: CostSeries[]; data: CostByProductPoint[] };
  costByCard: { series: CostSeries[]; data: CostByProductPoint[] };
  revenueByProduct: ProductBreakdown[];
  marginByProduct: ProductBreakdown[];
  customers: CustomerRow[];
  sparklines: SparklineSet;
}
