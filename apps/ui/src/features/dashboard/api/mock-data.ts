import type {
  StatsResponse,
  ChartsResponse,
  CustomersResponse,
  DailyChartPoint,
  StackedSeries,
  GroupBreakdown,
} from "./types";

// ─── Date helpers ────────────────────────────────────────────────────────────

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

// ─── Time series ─────────────────────────────────────────────────────────────

const days30 = generateDays(30);

// Raw dollar values per day (× 1_000_000 to convert to micros)
const M = 1_000_000;

const revenueTimeSeries: DailyChartPoint[] = days30.map((d, i) => {
  const revenueDollars = wave(280, 40, 0, i);
  const apiCostsDollars = wave(42, 8, 2, i);
  return {
    date: d.date,
    revenueMicros: Math.round(revenueDollars * M),
    apiCostsMicros: Math.round(apiCostsDollars * M),
    marginMicros: Math.round((revenueDollars - apiCostsDollars) * M),
  };
});

// ─── Stacked cost series (by group) ──────────────────────────────────────────

const groupSeries = [
  { key: "property_search", label: "Property search" },
  { key: "doc_summariser",  label: "Doc summariser" },
  { key: "content_gen",     label: "Content gen" },
];

const costByGroupData = days30.map((d, i) => ({
  date: d.date,
  property_search: Math.round(wave(28, 8, 0, i) * M),
  doc_summariser:  Math.round(wave(9, 3, 2, i) * M),
  content_gen:     Math.round(wave(4, 2, 5, i) * M),
}));

const costByGroup: StackedSeries = {
  series: groupSeries,
  data: costByGroupData,
};

// ─── Stacked cost series (by card) ───────────────────────────────────────────

const cardSeries = [
  { key: "gemini_2_flash", label: "Gemini 2.0 Flash" },
  { key: "claude_sonnet",  label: "Claude Sonnet" },
  { key: "gpt_4o",         label: "GPT-4o" },
  { key: "google_places",  label: "Google Places" },
  { key: "serper",         label: "Serper" },
];

const costByCardData = days30.map((d, i) => ({
  date: d.date,
  gemini_2_flash: Math.round(wave(23, 6, 0, i) * M),
  claude_sonnet:  Math.round(wave(10, 3, 2, i) * M),
  gpt_4o:         Math.round(wave(5, 1.5, 4, i) * M),
  google_places:  Math.round(wave(2, 0.8, 3, i) * M),
  serper:         Math.round(wave(1.2, 0.5, 1, i) * M),
}));

const costByCard: StackedSeries = {
  series: cardSeries,
  data: costByCardData,
};

// ─── Group breakdowns ─────────────────────────────────────────────────────────

const revenueByGroup: GroupBreakdown[] = [
  { key: "property_search", label: "Property search", valueMicros: 4_631_000_000, percentage: 55 },
  { key: "doc_summariser",  label: "Doc summariser",  valueMicros: 2_526_000_000, percentage: 30 },
  { key: "content_gen",     label: "Content gen",     valueMicros: 1_263_000_000, percentage: 15 },
];

const marginByGroup: GroupBreakdown[] = [
  { key: "property_search", label: "Property search", valueMicros: 3_783_000_000, percentage: 81.7 },
  { key: "doc_summariser",  label: "Doc summariser",  valueMicros: 2_252_000_000, percentage: 89.2 },
  { key: "content_gen",     label: "Content gen",     valueMicros: 1_138_000_000, percentage: 90.1 },
];

// ─── Sparklines (derived from time series) ───────────────────────────────────

const sparklineRevenue    = revenueTimeSeries.map((d) => d.revenueMicros);
const sparklineApiCosts   = revenueTimeSeries.map((d) => d.apiCostsMicros);
const sparklineGrossMargin = revenueTimeSeries.map((d) => d.marginMicros);
const sparklineMarginPct  = revenueTimeSeries.map((d) =>
  d.revenueMicros > 0
    ? Math.round(((d.revenueMicros - d.apiCostsMicros) / d.revenueMicros) * 1000) / 10
    : 0,
);
const sparklineCostPerRev = revenueTimeSeries.map((d) =>
  d.revenueMicros > 0
    ? Math.round((d.apiCostsMicros / d.revenueMicros) * 1000) / 1000
    : 0,
);

// ─── Exported mock shapes ─────────────────────────────────────────────────────

export const mockStats: StatsResponse = {
  revenueMicros:       8_420_000_000,
  apiCostsMicros:      1_247_000_000,
  grossMarginMicros:   7_173_000_000,
  marginPercentage:    85.2,
  costPerDollarRevenue: 0.148,
  revenuePrevChange:   14.2,
  costsPrevChange:     12.3,
  marginPrevChange:    14.5,
  marginPctPrevChange: 0.2,
  costPerRevPrevChange: -0.3,
  sparklines: {
    revenue:     sparklineRevenue,
    apiCosts:    sparklineApiCosts,
    grossMargin: sparklineGrossMargin,
    marginPct:   sparklineMarginPct,
    costPerRev:  sparklineCostPerRev,
  },
};

export const mockCharts: ChartsResponse = {
  revenueTimeSeries,
  costByGroup,
  costByCard,
  revenueByGroup,
  marginByGroup,
};

export const mockCustomers: CustomersResponse = {
  customers: [
    { customerId: "acme_corp",  externalId: "Acme Corp",           revenueMicros: 2_400_000_000, apiCostsMicros: 312_000_000, marginMicros: 2_088_000_000, marginPercentage: 87.0, eventCount: 14200 },
    { customerId: "brightpath", externalId: "BrightPath Ltd",      revenueMicros: 1_800_000_000, apiCostsMicros: 247_000_000, marginMicros: 1_553_000_000, marginPercentage: 86.3, eventCount: 11400 },
    { customerId: "novatech",   externalId: "NovaTech Inc",        revenueMicros:   950_000_000, apiCostsMicros: 189_000_000, marginMicros:   761_000_000, marginPercentage: 80.1, eventCount: 6800  },
    { customerId: "helios",     externalId: "Helios Digital",      revenueMicros:   720_000_000, apiCostsMicros: 198_000_000, marginMicros:   522_000_000, marginPercentage: 72.5, eventCount: 9400  },
    { customerId: "clearview",  externalId: "ClearView Analytics", revenueMicros:   150_000_000, apiCostsMicros: 142_000_000, marginMicros:     8_000_000, marginPercentage: 5.3,  eventCount: 8200  },
    { customerId: "eko",        externalId: "Eko Systems",         revenueMicros:    90_000_000, apiCostsMicros: 118_000_000, marginMicros:   -28_000_000, marginPercentage: -31.1, eventCount: 7900 },
  ],
};
