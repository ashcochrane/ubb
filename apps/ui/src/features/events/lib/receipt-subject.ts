// What a Pricing Receipt explains — `pricing_receipt_subject_type` — and what
// the receipt page says about each.
//
// The registry declares no console consumer for this concept and none is
// added here: a declared consumer is a file `domain-vocabulary/` names, and
// importing a generated set from `@/lib/vocabulary` moves no G2 verdict
// (#419). The catalogue has carried both words since the concept was coined;
// this is the first surface to render them (#425, spec §29), because #418
// made the second value producible — a delivered unit of work sold at one
// agreed price projects onto one posting, and the receipt that posting stores
// explains the CHARGE rather than the row it is stored on.
//
// THE SUBJECT DECIDES WHAT THE RECEIPT SECTION SAYS. A receipt with an empty
// costing detail and no per-quantity lines reads as a record with something
// missing from it, and for a charge nothing is: no supplier stands behind it
// and no rule priced it. The sentence has to say so before the record is
// shown, or the emptiness reads as a gap.

import { labelMap } from "@/lib/localisation";
import {
  PRICING_RECEIPT_SUBJECT_TYPE_LABEL_KEYS,
  type PricingReceiptSubjectType,
} from "@/lib/vocabulary";

/** The catalogue's name for what a receipt explains. */
export const pricingReceiptSubjectTypeLabel = labelMap(
  PRICING_RECEIPT_SUBJECT_TYPE_LABEL_KEYS,
);

/**
 * The sentence the Pricing receipt section opens with, per subject —
 * console-owned copy (ADR-0008 §4), total over the generated type so a subject
 * the registry adds and this has no sentence for fails `tsc` rather than
 * rendering nothing.
 *
 * The `usage_event` sentence is the one every receipt opened with before a
 * second subject existed, kept word for word: a receipt is the record of an
 * ECONOMIC RESOLUTION and every event has one, including on a workspace that
 * meters and does not bill, so the presence of a receipt must never be read
 * as proof that a customer was charged.
 */
export const RECEIPT_SUBJECT_EXPLANATIONS = {
  usage_event:
    "How UBB worked this event out — what it resolved, by which method, and as of when. Every event has one, including on a workspace that only meters: a receipt explains the amounts above, and is not evidence that a customer was charged.",
  charge:
    "How UBB worked this charge out. The whole unit of work was sold for one agreed price, settled before any of it ran, so this receipt names no measured quantity and no pricing rule — nothing is missing from it. The metered events under the same run each carry a receipt of their own, and none of them carries a customer price: the price is this one.",
} as const satisfies Record<PricingReceiptSubjectType, string>;

/**
 * The sentence for the subject a payload states, or for one it does not.
 *
 * `pricing_receipt_subject_type` is nullable on the wire — the serialiser
 * reads it out of the record, and a record in the older, unsectioned shape
 * names no subject — and a value the registry has never seen is legal on the
 * wire (ADR-003). Neither is a Charge, and both read as the ordinary case.
 */
export function receiptExplanation(subject: string | null | undefined): string {
  if (subject === "charge") return RECEIPT_SUBJECT_EXPLANATIONS.charge;
  return RECEIPT_SUBJECT_EXPLANATIONS.usage_event;
}
