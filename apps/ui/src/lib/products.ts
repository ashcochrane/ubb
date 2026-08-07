// The tenant-product surface: the registry's words, and the console's own copy.
//
// Identity lives in `@/lib/vocabulary` (generated from `domain-vocabulary/`),
// expression in `@/locales` reached through `@/lib/localisation`. This module
// is where the two meet for `tenant_product`, plus the one thing neither of
// them may hold.
//
// **The label is the registry's.** `productLabel` binds the generated label
// keys, so the words for a product are the catalogue's and an unfamiliar value
// renders as the token the server sent (ADR-0008 §4.3/§4.4). It replaces a
// hand-written map in `@/lib/labels` that fell back to the humaniser.
//
// **The description is the console's.** ADR-0008 §4.5: *"tooltips, empty-state
// prose, validation explanations and onboarding copy are never registry
// content"*, and a sentence explaining what a product does is exactly that. It
// is not a label key either: the catalogue's keys decompose into a declared
// concept prefix and a declared value of it, in both directions, and a
// per-product description key decomposes to a value no concept declares. So
// the copy lives here, keyed on the generated type, and `satisfies` makes a
// product with no sentence a compile error rather than a humanised guess.
//
// It sits in `lib/` rather than beside the settings feature because both
// consumers cannot share a feature: `components/shared/product-gate.tsx` is a
// layer below `features/settings`, and the console's imports only flow down.

import { labelMap } from "@/lib/localisation";
import {
  TENANT_PRODUCT_LABEL_KEYS,
  type TenantProduct,
} from "@/lib/vocabulary";

/** The catalogue's words for a product; the raw token for an unfamiliar one. */
export const productLabel = labelMap(TENANT_PRODUCT_LABEL_KEYS);

/**
 * What each product actually does, in a sentence — console-owned copy.
 *
 * Total over the generated type ON PURPOSE, and read by indexing rather than
 * through a lookup function: a product the registry declares and this constant
 * has no sentence for must fail `tsc`, which is the whole difference between
 * this and the map it replaces. There is no fallback to fall back to.
 */
export const PRODUCT_DESCRIPTIONS = {
  metering: "Usage events, pricing, analytics, and the audit trail.",
  billing: "Wallets, credit grants, budgets, invoices, and spend control.",
  referrals: "Referral programs, attribution, rewards, and payouts.",
} as const satisfies Record<TenantProduct, string>;
