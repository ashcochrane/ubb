// A postpaid customer's usage invoice: the registry's words for its status
// and for why it was skipped.
//
// Identity lives in `@/lib/vocabulary` (generated from `domain-vocabulary/`),
// expression in `@/locales` reached through `@/lib/localisation` — the
// `@/lib/products` pattern. Declared in R10-W4 (slice 8), which deleted the
// hand-written map in `@/lib/labels` this replaces; that map fell back to the
// humaniser, which ADR-0008 §4.3 calls a defect. The registry names this file
// as the console's consumer of the concept(s) below.
//
// It sits in `lib/` because two features render a usage invoice: the Billing
// page's card and the customer's own section. The skip reason was humanised
// in both (`g6-humanises-usage-invoices-card`, `-section`); it is a closed
// concept now, present only on a skipped invoice and null on every other one.

import { labelMap } from "@/lib/localisation";
import {
  SKIP_REASON_LABEL_KEYS,
  USAGE_INVOICE_STATUS_LABEL_KEYS,
} from "@/lib/vocabulary";

/** The catalogue's words for a usage invoice's status. */
export const usageInvoiceStatusLabel = labelMap(USAGE_INVOICE_STATUS_LABEL_KEYS);

/** The catalogue's words for why a usage invoice was skipped. */
export const skipReasonLabel = labelMap(SKIP_REASON_LABEL_KEYS);
