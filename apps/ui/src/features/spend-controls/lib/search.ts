// URL-backed state for the Spend controls tab. Every filter lives in the
// search string so a narrowed view is a link a colleague can be sent — the
// events ledger's shape; zod `.catch` keeps a mangled URL from ever crashing
// the route: a family the registry does not declare is no filter at all, and
// a report the tab does not have is the first one.

import { z } from "zod";

import { dateRangeSearchSchema } from "@/lib/date-range";
import { CONTROL_FAMILY_VALUES } from "@/lib/vocabulary";

/**
 * The two reports the tab hosts (#467), as the URL names them. Console route
 * state, not a registry concept: nothing on the wire carries these words.
 * The first is the default and is left out of the URL, as the customer
 * page leaves out its Overview tab.
 */
export const SPEND_CONTROL_REPORTS = ["stops", "utilisation"] as const;
export type SpendControlReport = (typeof SPEND_CONTROL_REPORTS)[number];

export const spendControlsSearchSchema = dateRangeSearchSchema.extend({
  customer_id: z.string().min(1).optional().catch(undefined),
  control_family: z.enum(CONTROL_FAMILY_VALUES).optional().catch(undefined),
  report: z.enum(SPEND_CONTROL_REPORTS).optional().catch(undefined),
});

export type SpendControlsSearch = z.infer<typeof spendControlsSearchSchema>;
