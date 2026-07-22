export type TimeRange = "7d" | "30d" | "90d" | "YTD";

export interface Sparklines {
  revenue: number[];          // micros
  apiCosts: number[];         // micros
  grossMargin: number[];      // micros
  marginPct: number[];
  costPerRev: number[];
}

export interface StatsResponse {
  revenueMicros: number;
  apiCostsMicros: number;
  grossMarginMicros: number;
  marginPercentage: number;
  costPerDollarRevenue: number;
  revenuePrevChange: number;
  costsPrevChange: number;
  marginPrevChange: number;
  marginPctPrevChange: number;
  costPerRevPrevChange: number;
  sparklines: Sparklines;
}

export interface DailyChartPoint {
  date: string;
  revenueMicros: number;
  apiCostsMicros: number;
  marginMicros: number;
}

export interface StackedSeries {
  series: { key: string; label: string }[];
  data: Array<{ date: string; [key: string]: number | string }>;
}

export interface GroupBreakdown {
  key: string;
  label: string;
  valueMicros: number;
  percentage: number;
}

export interface ChartsResponse {
  revenueTimeSeries: DailyChartPoint[];
  costByGroup: StackedSeries;
  costByCard: StackedSeries;
  revenueByGroup: GroupBreakdown[];
  marginByGroup: GroupBreakdown[];
}

export interface DashboardCustomerRow {
  customerId: string;
  externalId: string;
  revenueMicros: number;
  apiCostsMicros: number;
  marginMicros: number;
  marginPercentage: number;
  eventCount: number;
}

export interface CustomersResponse {
  customers: DashboardCustomerRow[];
}
