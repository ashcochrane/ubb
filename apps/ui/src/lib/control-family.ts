// The four spend-control families' words (#466; lifted here in #468).
//
// Identity lives in `@/lib/vocabulary` (generated from `domain-vocabulary/`),
// expression in `@/locales` reached through `@/lib/localisation`; this module
// is where the two meet for `control_family`, the `@/lib/products` shape. The
// binding was written in `features/spend-controls/lib/families.ts` (#466)
// while Stops and breaches was the one component rendering a family word,
// and moved here the day other features rendered one — the customer's
// Billing tab and the settings floors form head their sections with two of
// the four (#468), and the webhook picker heads two of its groups with the
// same two — the rule `@/lib/pricing-mode` states (#425). What each family
// MEANS stays with the reports that explain it, in that feature's `lib/`.
//
// The two headings below are the same catalogue words, derived rather than
// spelled: a surface that hand-types "Wallet policy" beside a binding that
// already words it has two spellings of one fact, and only one of them
// follows the catalogue.

import { labelMap } from "@/lib/localisation";
import { CONTROL_FAMILY_LABEL_KEYS } from "@/lib/vocabulary";

/** The catalogue's words for a family; the raw token for an unfamiliar one. */
export const controlFamilyLabel = labelMap(CONTROL_FAMILY_LABEL_KEYS);

/** The Customer Spend Pool's word — the heading of its pair wherever it renders. */
export const CUSTOMER_SPEND_POOL_TITLE = controlFamilyLabel("customer_spend_pool");

/** Wallet policy's word — the heading over the floors wherever they render. */
export const WALLET_POLICY_TITLE = controlFamilyLabel("wallet_policy");
