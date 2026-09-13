// The four spend controls as this feature names and explains them (#466;
// slice 6 §18).
//
// Identity lives in `@/lib/vocabulary` (generated from `domain-vocabulary/`),
// expression in `@/locales` reached through `@/lib/localisation`. This module
// is where the two meet for `control_family` — the `@/lib/products` shape —
// plus the one thing neither of them may hold: what each family means for the
// person reading a report, and why one of the four never has an episode.
//
// THIS IS THE PAYMENT OF `g2-console-control_family` AND
// `g6-map-past-limit-family-label` TOGETHER, in the shape #424 established:
// the hand-written map in `@/lib/labels` is deleted (it worded three
// report-local spellings of a family of four); that file holds the value list
// by reference, because the registry names it the console's consumer; the
// words have been in the catalogue under `control_family.*` since the concept
// was coined; and `controlFamilyLabel` below is the binding. A value list and
// the words for it cannot honestly move apart, which is why the two entries
// die in one commit.
//
// THE BINDING SITS IN THIS FEATURE'S `lib/` because Stops and breaches is the
// one component that renders a family word — on its own tab and, injected by
// the customer route, on the customer's Usage tab (the same component, not a
// second reader). It moves to `@/lib/` the day another feature renders the
// word, as `@/lib/pricing-mode` did in #425.

import { labelMap } from "@/lib/localisation";
import { CONTROL_FAMILY_LABEL_KEYS, type ControlFamily } from "@/lib/vocabulary";

/** The catalogue's words for a family; the raw token for an unfamiliar one. */
export const controlFamilyLabel = labelMap(CONTROL_FAMILY_LABEL_KEYS);

/**
 * What each family bounds, in a sentence — console-owned copy (ADR-0008 §4.5),
 * total over the generated type so a family the registry adds and this has
 * no sentence for fails `tsc` rather than rendering nothing.
 */
export const CONTROL_FAMILY_EXPLANATIONS = {
  ceiling:
    "A bound on one unit of work's own supplier cost. When the known total reaches it, UBB stops that unit and nothing else.",
  customer_spend_pool:
    "A bound on one customer's charges over a period. When the period's charges cross its stop line, new starts are refused and active work is stopped.",
  wallet_policy:
    "The floors under a customer's balance. The hard floor stops the customer; the soft floor only winds new starts down and stops nothing.",
  admission_control:
    "A bound on how fast new work may start. It refuses a start before any work runs and says nothing about supplier cost.",
} as const satisfies Record<ControlFamily, string>;

/**
 * Why a family filter answered no rows — the sentence under the empty state.
 *
 * ⚠ `admission_control` RENDERS AS NO ROWS, NEVER AS A DEFECT (spec §6, §18).
 * The reports itemise what was spent past a stop; a refused start spent
 * nothing, so admission control has no episodes to list and the empty answer
 * is the right one. The other three say the ordinary thing: nothing fired in
 * this window. Total over the generated type for the reason above.
 */
export const NO_EPISODES_FOR = {
  ceiling: "No unit of work was stopped on its own ceiling in this window.",
  customer_spend_pool: "No customer spend pool crossed its stop line in this window.",
  wallet_policy: "No wallet floor was crossed in this window.",
  admission_control:
    "Admission control refuses a start before any work runs, so it never has an episode to itemise. Nothing was spent past it — this is not an error.",
} as const satisfies Record<ControlFamily, string>;
