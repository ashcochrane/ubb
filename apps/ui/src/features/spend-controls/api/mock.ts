// Mock implementation — same exported signatures as ./api.ts, over the
// composed episodes. The customer and family filters are honoured; the window
// is echoed and not applied, for the reason `./mock-data` gives.

import { mockDelay } from "@/lib/api-provider";

import { MOCK_EPISODES, MOCK_MARGIN_CUSTOMERS, totalsOf } from "./mock-data";
import type { MarginCustomers, StopsAndBreaches, StopsAndBreachesFilters } from "./types";

const REPORT_WINDOW_MAX_DAYS = 366;

/** The window the route applies when the caller leaves it open: the 366 days ending now. */
function boundedWindow(filters: StopsAndBreachesFilters): { since: string; until: string } {
  const until = filters.until ?? new Date().toISOString();
  const since =
    filters.since ??
    new Date(Date.parse(until) - REPORT_WINDOW_MAX_DAYS * 86_400_000).toISOString();
  return { since, until };
}

export async function getStopsAndBreaches(
  filters: StopsAndBreachesFilters,
): Promise<StopsAndBreaches> {
  await mockDelay();
  const rows = MOCK_EPISODES.filter(
    (row) =>
      (filters.customer_id === undefined || row.customer_id === filters.customer_id) &&
      (filters.control_family === undefined || row.control_family === filters.control_family),
  );
  return { ...boundedWindow(filters), rows, totals: totalsOf(rows) };
}

export async function listCustomers(): Promise<MarginCustomers> {
  await mockDelay();
  return MOCK_MARGIN_CUSTOMERS;
}
