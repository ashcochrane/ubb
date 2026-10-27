// The billing-mode surface: the registry's words, and the console's own copy.
//
// Identity lives in `@/lib/vocabulary` (generated from `domain-vocabulary/`),
// expression in `@/locales` reached through `@/lib/localisation`. This module
// is where the two meet for `customer_billing_mode` and the `tenant_posture`
// derived from it — `@/lib/products` is the pattern. It replaces two
// hand-written maps in `@/lib/labels` that fell back to the humaniser (slice 8).
//
// It sits in the settings feature's `lib/` because only the settings cards
// render these words; it moves to `src/lib/` the day a second feature does.

import { labelMap } from "@/lib/localisation";
import {
  CUSTOMER_BILLING_MODE_LABEL_KEYS,
  TENANT_POSTURE_LABEL_KEYS,
  type CustomerBillingMode,
} from "@/lib/vocabulary";

/** The catalogue's words for a billing mode; the raw token for an unfamiliar one. */
export const billingModeLabel = labelMap(CUSTOMER_BILLING_MODE_LABEL_KEYS);

/** The catalogue's words for the posture the server derives from the mode. */
export const tenantPostureLabel = labelMap(TENANT_POSTURE_LABEL_KEYS);

/**
 * What each billing mode does, in a sentence — console-owned copy
 * (ADR-0008 §4.5), total over the generated type so a mode with no sentence
 * fails `tsc` rather than reaching a humanised guess.
 */
export const BILLING_MODE_DESCRIPTIONS = {
  external:
    "Track usage, provider cost, and margin, and bill your customers elsewhere. No money moves in UBB.",
  prepaid:
    "Customers hold prepaid credit; usage draws the balance down in real time.",
  postpaid:
    "Usage accrues per period and is pushed to Stripe as invoice line items at period close.",
} as const satisfies Record<CustomerBillingMode, string>;
