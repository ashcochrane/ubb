// The words a supplied revenue figure is read under (#508; slice 7 §5, §9).
//
// ⚠ **IN `src/lib` RATHER THAN A FEATURE's, BECAUSE TWO FEATURES RENDER THESE
// WORDS.** It began in the customers feature, which is where the supplied
// record's own panels live; the billing revenue section renders the BASIS too,
// because the one economic query states which view it served and a chart
// summing supplied amounts under it must say so. `apps/ui/CLAUDE.md` is
// explicit that a concept's module moves here the day a second feature renders
// its word, since imports only flow down and no feature may reach into
// another.
//
// Two registry concepts meet on one panel, and keeping them apart is the point
// of this module:
//
//   * `revenue_basis` — WHICH OF THE TWO VIEWS a figure is stated under. It is
//     a property of the QUESTION the surface asked, the same for every row on
//     screen, and the answer carries it back so nothing has to assume.
//   * `recognition_method` — HOW ONE RECORD is spread over the span it
//     declares. It is a property of the RECORD, stated by the tenant when they
//     supplied it, and two rows in one answer may differ.
//
// ⚠ **THE LABELS ARE BOUND ONCE, FROM THE GENERATED KEYS, AND THE CATALOGUE
// OWNS THE ENGLISH** (ADR-0008 §4). Both concepts are `closed` — UBB owns the
// whole value set — so `labelMap` is the right binding and `open-set-value` is
// not: there is no such thing as a basis this build has not met.
//
// ⚠ **THE SENTENCES BESIDE THEM ARE CONSOLE COPY AND HAVE NO LABEL KEY.**
// ADR-0008 §4.5 rules explanatory prose out of the catalogue, and G6 would
// refuse the keys anyway: a key must decompose into a declared concept prefix
// and a declared VALUE of it, and "what this method does to your number" is
// neither. They are `Record`s total over the generated unions, so a third
// recognition method is a `tsc` failure here rather than a value that renders
// with its word and no explanation.

import { labelMap } from "@/lib/localisation";
import {
  RECOGNITION_METHOD_LABEL_KEYS,
  REVENUE_BASIS_LABEL_KEYS,
  type RecognitionMethod,
  type RevenueBasis,
} from "@/lib/vocabulary";

/** How one supplied record is spread over the span it declares. */
export const recognitionMethodLabel = labelMap(RECOGNITION_METHOD_LABEL_KEYS);

/** Which of the two views a revenue figure is stated under. */
export const revenueBasisLabel = labelMap(REVENUE_BASIS_LABEL_KEYS);

/**
 * What choosing each basis does to the figures on screen.
 *
 * ⚠ **BOTH SENTENCES SAY WHETHER ANYTHING IS DIVIDED, because that is the whole
 * difference and it is the thing slice 7 §5 refuses to leave unsaid.** Today's
 * revenue helpers prorated by day unconditionally and unlabelled, with no way
 * to ask for the undivided figure — so *recognised* is the behaviour UBB always
 * had and *recorded* is the one that was missing. A tenant has to be able to
 * see which they are looking at.
 */
export const REVENUE_BASIS_MEANS: Record<RevenueBasis, string> = {
  recorded:
    "Each figure whole, on the day its own period opens. Nothing is divided.",
  recognised:
    "Each figure spread across the period it covers, by the method stated on it.",
};

/** What each recognition method does to an amount over the span it covers. */
export const RECOGNITION_METHOD_MEANS: Record<RecognitionMethod, string> = {
  straight_line:
    "Divided evenly by day across the period this covers.",
  on_receipt:
    "Landed whole on the day the period opens — an up-front amount, not a rate.",
};

/**
 * Whether a method divides an amount across the span the record declares.
 *
 * ⚠ **THE SAME QUESTION THE SERVER ASKS BEFORE IT WRITES**, and the reason the
 * console asks it too is that the answer changes what the two bases show: a
 * method that divides nothing makes *recorded* and *recognised* the same figure
 * for that row, which the panel says rather than leaving a reader to notice
 * that two columns happen to match.
 *
 * Total over the generated union for the same reason as the maps above.
 */
const SPREADS_ACROSS_ITS_SPAN: Record<RecognitionMethod, boolean> = {
  straight_line: true,
  on_receipt: false,
};

export function spreadsAcrossItsSpan(method: string): boolean {
  return SPREADS_ACROSS_ITS_SPAN[method as RecognitionMethod] ?? false;
}

/**
 * What a chart is saying about its own revenue figures, in one sentence.
 *
 * ⚠ **AN AGGREGATE CANNOT CARRY A SOURCE REFERENCE, BUT IT CAN CARRY ITS
 * BASIS, AND §5 SAYS IT MUST.** A supplied amount reaching a total has been
 * placed whole on one day or spread across its period, and the tenant "must be
 * able to see whether they are looking at smoothing they did not ask for". The
 * per-record panels answer that with a method and a reference per row; a chart
 * summing three revenue sources has neither to show, so what it owes is the
 * view it was drawn under — which the answer itself states.
 *
 * Unrecognised values fall to the token, marked by the caller: `revenue_basis`
 * is closed, so this is the branch that should never run, and inventing
 * English for it would be exactly the guess ADR-0008 §4.3 forbids.
 */
export function revenueBasisNote(basis: string): string {
  const meaning = REVENUE_BASIS_MEANS[basis as RevenueBasis];
  const named = revenueBasisLabel(basis);
  return meaning === undefined
    ? `Revenue stated on the ${named} basis.`
    : `Revenue stated as ${named.toLowerCase()} — ${meaning.toLowerCase()}`;
}
