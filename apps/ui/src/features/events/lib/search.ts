// URL-backed state for the events ledger. Every filter lives in the search
// string so views are shareable/bookmarkable; zod `.catch` keeps a mangled
// URL from ever crashing the route.

import { z } from "zod";

import { dateRangeSearchSchema } from "@/lib/date-range";
import { isGroupingAxis } from "@/lib/grouping-axis";

export const STOP_SCOPES = ["task", "subtask", "customer"] as const;

export const eventsSearchSchema = dateRangeSearchSchema.extend({
  customer_id: z.string().min(1).optional().catch(undefined),
  // ⚠ **THE PAIR NAMES THE BAG IT READS, AND THE URL IS PART OF THAT (#507).**
  // It carried the analytics grouping word until now — an axis word over a bag
  // ADR-0005 keeps deliberately ungroupable — while the route it reaches has
  // named the bag since #504. A bookmark saved under the old spelling keeps
  // working and loses its filter: an unknown search key is dropped here, so the
  // ledger opens unfiltered with both inputs visibly empty, which is a state a
  // reader can see and correct. That is the same answer `group_by` below gives
  // a stale bookmark, and it is only tolerable because this filter is on the
  // screen; the wire-level version of it is the silent widening #504 recorded.
  metadata_key: z.string().min(1).optional().catch(undefined),
  metadata_value: z.string().min(1).optional().catch(undefined),
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

/** A change to the ledger's filters, as the bar hands one back to the page. */
export interface FilterPatch {
  past_limit?: boolean;
  stop_scope?: EventsSearch["stop_scope"];
  episode_seq?: number;
  metadata_key?: string;
  metadata_value?: string;
}

/**
 * Every filter, cleared.
 *
 * ⚠ **ONE LITERAL, BECAUSE A FILTER LEFT OUT OF IT SURVIVES THE CLICK.** The
 * filter bar and the empty state below the table both offer "Clear filters",
 * and both spelled these five keys out. A patch that omits one leaves that
 * filter applied while the bar stops claiming anything is active — and the
 * rename in #507 had to edit the same five keys in two files, which is how the
 * duplication announced itself. The type is what makes it total: every key of
 * the patch, each set to nothing, so a filter added to `FilterPatch` and not to
 * this object is a `tsc` failure rather than a key that quietly stops being
 * cleared.
 *
 * It lives here rather than beside the bar because a file that exports a
 * component may export nothing else — `react-refresh/only-export-components` is
 * an ERROR in this console, and this module already owns the filter vocabulary
 * it is made of.
 */
export const NO_FILTERS: Record<keyof FilterPatch, undefined> = {
  past_limit: undefined,
  stop_scope: undefined,
  episode_seq: undefined,
  metadata_key: undefined,
  metadata_value: undefined,
};

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

