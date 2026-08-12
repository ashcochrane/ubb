// What a posting's measurement status is called, and what it means for the
// person reading the receipt.
//
// Identity is the registry's (`@/lib/vocabulary`), expression the catalogue's
// (`@/locales`, reached through `@/lib/localisation`) — the same split
// `@/lib/products` makes for `tenant_product`, and for the same reason. What is
// console-owned is the sentence BESIDE the name: ADR-0008 §4 rules that
// *"tooltips, empty-state prose, validation explanations and onboarding copy
// are never registry content"*, and a per-status explanation is exactly that.
// It is not a label key either, since a catalogue key must decompose into a
// declared concept prefix and a declared value of it in both directions.
//
// §4 HAS NO SUB-SECTIONS. Several sites in this repo cite "§4.3"/"§4.4"/"§4.5"
// and none of them exists; the shorthand is not propagated here.
//
// This lives in the events feature rather than in `lib/` because the receipt is
// its only reader. `@/lib/products` states the opposite rule for itself and the
// two agree: it sits in `lib/` precisely because its two consumers span layers
// that cannot share a feature.

import { labelMap } from "@/lib/localisation";
import {
  MEASUREMENTS_STATUS_LABEL_KEYS,
  type MeasurementsStatus,
} from "@/lib/vocabulary";

/** The catalogue's name for a measurement status. */
export const measurementsStatusLabel = labelMap(MEASUREMENTS_STATUS_LABEL_KEYS);

/**
 * Why the quantities below are — or are not — there, in a sentence.
 *
 * Total over the generated type ON PURPOSE and read by indexing rather than
 * through a lookup: a status the registry declares and this constant has no
 * sentence for is a `tsc` failure, which is the difference between console copy
 * and a guess. The set is closed and final, so the compile error is the whole
 * safety net it needs.
 */
export const MEASUREMENTS_STATUS_EXPLANATIONS = {
  available: "The measured quantities this event was priced on.",
  pruned:
    "This event was measured. The detail has since passed its retention horizon and been removed, so the quantities can no longer be shown — this is not a record of zero usage.",
  not_applicable:
    "This posting was sold for one agreed price rather than priced on measured quantities, so it never had any to show.",
} as const satisfies Record<MeasurementsStatus, string>;

/**
 * The one sentence a pruned payload must never be given.
 *
 * It belongs to a metered posting whose measurement record is present and holds
 * nothing — `available` with an empty bag — and it is a lie about a posting
 * whose record was removed on schedule. Naming it is what lets the receipt's
 * test assert its ABSENCE from the pruned case: a rendering defect here does
 * not throw and does not fail a type check, so the only thing that catches it
 * is an assertion that can point at the wrong words.
 */
export const NO_QUANTITIES_RECORDED =
  "No measured quantities were recorded for this event.";
