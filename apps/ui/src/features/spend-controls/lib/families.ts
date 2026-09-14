// The four spend controls as this feature explains them (#466; slice 6 §18):
// what each family means for the person reading a report, and why one of the
// four never has an episode — the one thing neither the registry nor the
// catalogue may hold (ADR-0008 §4.5).
//
// THE WORDS THEMSELVES ARE `@/lib/control-family`'s. `g2-console-
// control_family` and `g6-map-past-limit-family-label` were paid together
// in #466, in the shape #424 established — the hand-written map in
// `@/lib/labels` deleted, that file holding the value list by reference, the
// words in the catalogue under `control_family.*`, and `controlFamilyLabel`
// the binding — and the binding sat HERE while Stops and breaches was the one
// component rendering a family word. It moved to `@/lib/` in #468, the day
// the customer's Billing tab and the settings floors form headed their
// sections with two of the four, as this header said it would.

import type { ControlFamily } from "@/lib/vocabulary";

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
