// URL-backed state for the events ledger. Every filter lives in the search
// string so views are shareable/bookmarkable; zod `.catch` keeps a mangled
// URL from ever crashing the route.

import { z } from "zod";

import { dateRangeSearchSchema, type DateRange } from "@/lib/date-range";
import { TIMESERIES_GROUP_BY } from "@/lib/labels";

export const STOP_SCOPES = ["task", "subtask", "customer"] as const;

export const eventsSearchSchema = dateRangeSearchSchema.extend({
  customer_id: z.string().min(1).optional().catch(undefined),
  tag_key: z.string().min(1).optional().catch(undefined),
  tag_value: z.string().min(1).optional().catch(undefined),
  past_limit: z.boolean().optional().catch(undefined),
  stop_scope: z.enum(STOP_SCOPES).optional().catch(undefined),
  episode_seq: z.number().int().nonnegative().optional().catch(undefined),
  group_by: z.enum(TIMESERIES_GROUP_BY).optional().catch(undefined),
});

export type EventsSearch = z.infer<typeof eventsSearchSchema>;

// The event detail (GET /metering/usage/{event_id}) does NOT carry the
// customer's id, but the refund endpoint needs it — so the ledger link
// forwards it as a search param. Arriving without it hides the refund action.
export const eventDetailSearchSchema = z.object({
  customer_id: z.string().min(1).optional().catch(undefined),
});

export type EventDetailSearch = z.infer<typeof eventDetailSearchSchema>;

/** First 8 characters of a UUID for compact display ("7f3c2a10…"). */
export function shortId(id: string): string {
  return id.length > 8 ? `${id.slice(0, 8)}…` : id;
}

/**
 * Map the inclusive calendar-date analytics window onto the past-limit
 * report's datetime window: since = start-of-start-day, until = start of the
 * day AFTER the end date (the report uses `>= since, < until`).
 */
export function pastLimitWindow(range: Required<DateRange>): {
  since: string;
  until: string;
} {
  const next = new Date(`${range.end_date}T00:00:00Z`);
  next.setUTCDate(next.getUTCDate() + 1);
  return {
    since: `${range.start_date}T00:00:00Z`,
    until: `${next.toISOString().slice(0, 10)}T00:00:00Z`,
  };
}
