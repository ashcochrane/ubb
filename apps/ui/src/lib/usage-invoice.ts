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
//
// `below_minor_unit` (R10 Stage C3, F-9) is the month whose usage, with the
// sub-cent amount carried in from earlier months, still came to less than one
// minor unit: no Stripe invoice was issued and the amount was carried forward.
// Such a month was shown as pushed with no invoice id before; a pushed invoice
// now always has one. It renders through the same label map as every reason.

//
// `payment_status` (R10 Stage C5, F-15) is where the Stripe invoice behind a
// pushed usage invoice stands as a receivable — open, paid, void or
// uncollectible — a closed concept the registry names this file as the
// consumer of. It is NULL while the invoice is not yet collectible: no Stripe
// invoice issued for it, or none has reported a status yet. Null is that
// meaning, not a fifth value, so its wording is console-owned explanatory copy
// beside the label (ADR-0008 §4.5), never a catalogue key.

import { labelMap } from "@/lib/localisation";
import {
  SKIP_REASON_LABEL_KEYS,
  USAGE_INVOICE_PAYMENT_STATUS_LABEL_KEYS,
  USAGE_INVOICE_STATUS_LABEL_KEYS,
} from "@/lib/vocabulary";

/** The catalogue's words for a usage invoice's status. */
export const usageInvoiceStatusLabel = labelMap(USAGE_INVOICE_STATUS_LABEL_KEYS);

/** The catalogue's words for why a usage invoice was skipped. */
export const skipReasonLabel = labelMap(SKIP_REASON_LABEL_KEYS);

/** The catalogue's words for where a pushed invoice stands as a receivable. */
export const usageInvoicePaymentStatusLabel = labelMap(
  USAGE_INVOICE_PAYMENT_STATUS_LABEL_KEYS,
);

/** What a null `payment_status` means — not a value, so not a label key. */
export const NOT_YET_COLLECTIBLE = "Not yet collectible";

/**
 * The words for a usage invoice's `payment_status`, null included: a value
 * renders through the label map, and null renders as the one thing null
 * means on this field.
 */
export function paymentStatusWording(status: string | null | undefined): string {
  return status == null ? NOT_YET_COLLECTIBLE : usageInvoicePaymentStatusLabel(status);
}
