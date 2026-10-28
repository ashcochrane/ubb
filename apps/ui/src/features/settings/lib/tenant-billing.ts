// UBB's own billing of the tenant: the registry's words for a billing
// period's status and a tenant invoice's.
//
// Identity lives in `@/lib/vocabulary` (generated from `domain-vocabulary/`),
// expression in `@/locales` reached through `@/lib/localisation` — the
// `@/lib/products` pattern. Declared in R10-W4 (slice 8), which deleted the
// hand-written map in `@/lib/labels` this replaces; that map fell back to the
// humaniser, which ADR-0008 §4.3 calls a defect. The registry names this file
// as the console's consumer of the concept(s) below.

import { labelMap } from "@/lib/localisation";
import {
  BILLING_PERIOD_STATUS_LABEL_KEYS,
  TENANT_INVOICE_STATUS_LABEL_KEYS,
} from "@/lib/vocabulary";

/** The catalogue's words for a billing period's status. */
export const billingPeriodStatusLabel = labelMap(BILLING_PERIOD_STATUS_LABEL_KEYS);

/** The catalogue's words for a tenant invoice's status. */
export const tenantInvoiceStatusLabel = labelMap(TENANT_INVOICE_STATUS_LABEL_KEYS);
