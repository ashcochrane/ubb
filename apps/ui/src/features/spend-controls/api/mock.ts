// Mock implementation — same exported signatures as ./api.ts, over the
// composed episodes. The customer and family filters are honoured; the window
// is echoed and not applied, for the reason `./mock-data` gives.

import { mockDelay } from "@/lib/api-provider";
import type { DatetimeWindow } from "@/lib/date-range";

import {
  CUSTOMER_ACME,
  MOCK_EPISODES,
  MOCK_MARGIN_CUSTOMERS,
  MOCK_UTILISATION_ROWS,
  POOL_STATUS_ACME,
  totalsOf,
  utilisationReport,
} from "./mock-data";
import type {
  MarginCustomers,
  StopsAndBreaches,
  StopsAndBreachesFilters,
  UtilisationAndHeadroom,
  UtilisationAndHeadroomFilters,
} from "./types";

/** The route's own bound (`core.time_windows.REPORT_WINDOW_MAX_DAYS`), mirrored so the mock echoes what the server would. */
const REPORT_WINDOW_MAX_DAYS = 366;

/** The window the route applies when the caller leaves it open: the 366 days ending now. */
function boundedWindow(filters: Partial<DatetimeWindow>): DatetimeWindow {
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

/**
 * The customer filter is honoured; the pool pair answers for the one
 * customer of the story with a pool, as the route answers it only for a
 * named customer with a pool that applies.
 */
export async function getUtilisationAndHeadroom(
  filters: UtilisationAndHeadroomFilters,
): Promise<UtilisationAndHeadroom> {
  await mockDelay();
  const rows = MOCK_UTILISATION_ROWS.filter(
    (row) => filters.customer_id === undefined || row.customer_id === filters.customer_id,
  );
  const pool = filters.customer_id === CUSTOMER_ACME ? POOL_STATUS_ACME : null;
  return utilisationReport(rows, boundedWindow(filters), pool);
}

export async function listCustomers(): Promise<MarginCustomers> {
  await mockDelay();
  return MOCK_MARGIN_CUSTOMERS;
}
