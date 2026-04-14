import type {
  DashboardData,
  RevenueTimeSeries,
  CostByProductPoint,
  CostSeries,
  ProductBreakdown,
  CustomerRow,
  StatsData,
  SparklineSet,
} from "./types";

function generateDays(count: number): { date: string; label: string }[] {
  const days: { date: string; label: string }[] = [];
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  // Fixed date so data is deterministic
  const now = new Date(2026, 2, 20); // 20 Mar 2026
  for (let i = count - 1; i >= 0; i--) {
    const d = new Date(now);
    d.setDate(d.getDate() - i);
    const date = d.toISOString().split("T")[0]!;
    const label = `${d.getDate()} ${months[d.getMonth()]!}`;
    days.push({ date, label });
  }
  return days;
}

/** Deterministic wave — no Math.random(). */
function wave(base: number, amplitude: number, phase: number, day: number): number {
  const noise = Math.sin(day * 3.7 + phase * 11.3) * amplitude * 0.2;
  return Math.max(0, Math.round((base + amplitude * Math.sin((day + phase) * 0.22) + noise) * 100) / 100);
}

const days30 = generateDays(30);

const revenueTimeSeries: RevenueTimeSeries[] = days30.map((d, i) => {
  const revenue = wave(280, 40, 0, i);
  const apiCosts = wave(42, 8, 2, i);
  return {
    ...d,
    revenue,
    apiCosts,
    margin: Math.round((revenue - apiCosts) * 100) / 100,
  };
});

const productSeries: CostSeries[] = [
  { key: "property_search", label: "Property search", color: "#4a7fa8" },
  { key: "doc_summariser", label: "Doc summariser", color: "#6a5aaa" },
  { key: "content_gen", label: "Content gen", color: "#b84848" },
];

const costByProductData: CostByProductPoint[] = days30.map((d, i) => ({
  ...d,
  property_search: wave(28, 8, 0, i),
  doc_summariser: wave(9, 3, 2, i),
  content_gen: wave(4, 2, 5, i),
}));

const cardSeries: CostSeries[] = [
  { key: "gemini_2_flash", label: "Gemini 2.0 Flash", color: "#c0392b" },
  { key: "claude_sonnet",  label: "Claude Sonnet",    color: "#4a7fa8" },
  { key: "gpt_4o",         label: "GPT-4o",           color: "#484240" },
  { key: "google_places",  label: "Google Places",    color: "#a16a4a" },
  { key: "serper",         label: "Serper",           color: "#b5ad9e" },
];

const costByCardData: CostByProductPoint[] = days30.map((d, i) => ({
  ...d,
  gemini_2_flash: wave(23, 6, 0, i),
  claude_sonnet: wave(10, 3, 2, i),
  gpt_4o: wave(5, 1.5, 4, i),
  google_places: wave(2, 0.8, 3, i),
  serper: wave(1.2, 0.5, 1, i),
}));

// Hardcoded to match mockup values — consistent with stats
const revenueByProduct: ProductBreakdown[] = [
  { key: "property_search", label: "Property search", color: "#4a7fa8", value: 4631, percentage: 55 },
  { key: "doc_summariser",  label: "Doc summariser",  color: "#6a5aaa", value: 2526, percentage: 30 },
  { key: "content_gen",     label: "Content gen",     color: "#b84848", value: 1263, percentage: 15 },
];

// Use product colors for dots, bar color is separate (handled in component)
const marginByProduct: ProductBreakdown[] = [
  { key: "property_search", label: "Property search", color: "#4a7fa8", value: 3783, percentage: 81.7 },
  { key: "doc_summariser",  label: "Doc summariser",  color: "#6a5aaa", value: 2252, percentage: 89.2 },
  { key: "content_gen",     label: "Content gen",     color: "#b84848", value: 1138, percentage: 90.1 },
];

const customers: CustomerRow[] = [
  { name: "Acme Corp", customerId: "acme_corp", revenue: 2400, revenueType: "Sub", apiCosts: 312, margin: 2088, marginPercentage: 87.0, events: 14200 },
  { name: "BrightPath Ltd", customerId: "brightpath", revenue: 1800, revenueType: "Sub", apiCosts: 247, margin: 1553, marginPercentage: 86.3, events: 11400 },
  { name: "NovaTech Inc", customerId: "novatech", revenue: 950, revenueType: "Usage", apiCosts: 189, margin: 761, marginPercentage: 80.1, events: 6800 },
  { name: "Helios Digital", customerId: "helios", revenue: 720, revenueType: "Sub", apiCosts: 198, margin: 522, marginPercentage: 72.5, events: 9400 },
  { name: "ClearView Analytics", customerId: "clearview", revenue: 150, revenueType: "Usage", apiCosts: 142, margin: 8, marginPercentage: 5.3, events: 8200 },
  { name: "Eko Systems", customerId: "eko", revenue: 90, revenueType: "Usage", apiCosts: 118, margin: -28, marginPercentage: -31.1, events: 7900 },
];

// Hardcoded stats matching mockup
const stats: StatsData = {
  revenue: 8420,
  apiCosts: 1247,
  grossMargin: 7173,
  marginPercentage: 85.2,
  costPerDollarRevenue: 0.148,
  revenuePrevChange: 14.2,
  costsPrevChange: 12.3,
  marginPrevChange: 14.5,
  marginPctPrevChange: 0.2,
  costPerRevPrevChange: -0.3,
};

const sparklines: SparklineSet = {
  revenue:     revenueTimeSeries.map((d) => d.revenue),
  apiCosts:    revenueTimeSeries.map((d) => d.apiCosts),
  grossMargin: revenueTimeSeries.map((d) => d.margin),
  // marginPct rounded to 1 decimal place
  marginPct:   revenueTimeSeries.map((d) =>
    Math.round(((d.revenue - d.apiCosts) / d.revenue) * 1000) / 10,
  ),
  // costPerRev rounded to 3 decimal places
  costPerRev:  revenueTimeSeries.map((d) =>
    Math.round((d.apiCosts / d.revenue) * 1000) / 1000,
  ),
};

export const mockDashboardData: DashboardData = {
  stats,
  revenueTimeSeries,
  costByProduct: { series: productSeries, data: costByProductData },
  costByCard: { series: cardSeries, data: costByCardData },
  revenueByProduct,
  marginByProduct,
  customers,
  sparklines,
};
