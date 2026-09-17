// URL-backed state for the events ledger. Every filter lives in the search
// string so views are shareable/bookmarkable; zod `.catch` keeps a mangled
// URL from ever crashing the route.

import { z } from "zod";

import { dateRangeSearchSchema } from "@/lib/date-range";
import { isGroupingAxis } from "@/lib/grouping-axis";

export const STOP_SCOPES = ["task", "subtask", "customer"] as const;

export const eventsSearchSchema = dateRangeSearchSchema.extend({
  customer_id: z.string().min(1).optional().catch(undefined),
  tag_key: z.string().min(1).optional().catch(undefined),
  tag_value: z.string().min(1).optional().catch(undefined),
  past_limit: z.boolean().optional().catch(undefined),
  stop_scope: z.enum(STOP_SCOPES).optional().catch(undefined),
  episode_seq: z.number().int().nonnegative().optional().catch(undefined),
  // ⚠ A SHAPE CHECK, NOT A MEMBERSHIP ONE (#506). Which axes exist is this
  // tenant's own answer, computed per tenant and read off the discovery
  // contract, so a URL parser has no list to check against and the server
  // refuses an axis nobody declared. What this still catches is a URL carrying
  // the retired shape — a bare axis name the call site used to prefix — which
  // names no axis at all and would otherwise be forwarded verbatim.
  group_by: z.string().refine(isGroupingAxis).optional().catch(undefined),
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

