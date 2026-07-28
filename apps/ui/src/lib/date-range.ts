// Shared date-window model for the analytics/margin endpoints.
//
// The API takes `start_date` / `end_date` as inclusive YYYY-MM-DD calendar
// dates (UTC), windows capped at 366 days (92 for hourly timeseries). Margin
// endpoints default to month-to-date when omitted — the UI mirrors that
// default so both surfaces agree on "this month".

import { z } from "zod";

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

export const dateRangeSearchSchema = z.object({
  start_date: z.string().regex(DATE_RE).optional().catch(undefined),
  end_date: z.string().regex(DATE_RE).optional().catch(undefined),
});

export interface DateRange {
  start_date?: string;
  end_date?: string;
}

function toIsoDate(date: Date): string {
  return date.toISOString().slice(0, 10);
}

export function todayIso(): string {
  return toIsoDate(new Date());
}

export interface DateRangePreset {
  key: string;
  label: string;
  range: () => DateRange;
}

export const DATE_RANGE_PRESETS: DateRangePreset[] = [
  {
    key: "mtd",
    label: "Month to date",
    range: () => {
      const now = new Date();
      const first = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1));
      return { start_date: toIsoDate(first), end_date: todayIso() };
    },
  },
  {
    key: "7d",
    label: "Last 7 days",
    range: () => {
      const end = new Date();
      const start = new Date(end.getTime() - 6 * 86_400_000);
      return { start_date: toIsoDate(start), end_date: toIsoDate(end) };
    },
  },
  {
    key: "30d",
    label: "Last 30 days",
    range: () => {
      const end = new Date();
      const start = new Date(end.getTime() - 29 * 86_400_000);
      return { start_date: toIsoDate(start), end_date: toIsoDate(end) };
    },
  },
  {
    key: "90d",
    label: "Last 90 days",
    range: () => {
      const end = new Date();
      const start = new Date(end.getTime() - 89 * 86_400_000);
      return { start_date: toIsoDate(start), end_date: toIsoDate(end) };
    },
  },
];

/** The preset key matching a range, or "custom". */
export function matchPreset(range: DateRange): string {
  if (!range.start_date && !range.end_date) return "mtd";
  for (const preset of DATE_RANGE_PRESETS) {
    const candidate = preset.range();
    if (
      candidate.start_date === range.start_date &&
      candidate.end_date === range.end_date
    ) {
      return preset.key;
    }
  }
  return "custom";
}

/** Resolve an (optional) range to concrete dates, defaulting to month-to-date. */
export function resolveRange(range: DateRange): Required<DateRange> {
  const mtd = DATE_RANGE_PRESETS[0]!.range();
  return {
    start_date: range.start_date ?? mtd.start_date!,
    end_date: range.end_date ?? mtd.end_date!,
  };
}
