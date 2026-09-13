// URL-backed state for the Spend controls tab. Every filter lives in the
// search string so a narrowed view is a link a colleague can be sent — the
// events ledger's shape; zod `.catch` keeps a mangled URL from ever crashing
// the route: a family the registry does not declare is no filter at all.

import { z } from "zod";

import { dateRangeSearchSchema } from "@/lib/date-range";
import { CONTROL_FAMILY_VALUES } from "@/lib/vocabulary";

export const spendControlsSearchSchema = dateRangeSearchSchema.extend({
  customer_id: z.string().min(1).optional().catch(undefined),
  control_family: z.enum(CONTROL_FAMILY_VALUES).optional().catch(undefined),
});

export type SpendControlsSearch = z.infer<typeof spendControlsSearchSchema>;
