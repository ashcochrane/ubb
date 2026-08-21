// What the console may say about a customer price — and about one it does not
// have (#371, #155 §9.2).
//
// The price-side twin of `@/lib/supplier-cost`, and the two are deliberately
// symmetrical: an amount went nullable, so the amount alone stopped being able
// to say what it means, and something has to hold the rule about what the
// absence renders as. `#317` did that to the supplier cost and #330 wrote its
// module; #351 did it to the customer price and this is that module.
//
// ⚠ THE PRICE SIDE IS THE HARDER HALF, and this is the whole reason it needs
// its own file rather than three more exports over there. A NULL supplier cost
// is two states; a NULL customer price is THREE, and the third carries a cause
// of its own:
//
//     known           a figure, and the only one there is
//     unknown         information UBB does not have — the one a total is a
//                     floor because of, and the one a recovery run revisits
//     waived          a charge somebody decided not to pursue: a loss that was
//                     decided rather than a question still open
//     not_applicable  a subject that generates no customer revenue at this
//                     level, PLUS a `not_applicable_reason` saying which of two
//                     mutually exclusive causes it was
//
// **`waived` and `unknown` are exactly the two a naive zero-coalesce renders as
// a real number**, which is the defect the standing obligation exists to
// prevent. `const displayed = amount ?? 0` on either of them tells a tenant
// they charged their customer nothing — the unflattering direction of the
// identical mistake the supplier half makes in the flattering one.
//
// IDENTITY IS THE REGISTRY'S, EXPRESSION THE CATALOGUE'S — the split
// `@/lib/products`, `@/lib/supplier-cost` and `features/events/lib/measurements`
// all make. The value lists and the stable label keys come from
// `@/lib/vocabulary` (generated from `domain-vocabulary/`); the words hang off
// those keys in `@/locales`; and the SENTENCES below are console-owned copy,
// which ADR-0008 §4 rules is never registry content and never a label key —
// a catalogue key must decompose into a declared concept prefix and a declared
// value of it, in both directions, and "why there is no price here" decomposes
// to nothing.
//
// It sits in `lib/` rather than inside a feature because more than one feature
// reads it and they cannot share one: the event receipt is `features/events`,
// the developer console's recorded response is `features/developers`, and the
// console's imports only flow down. `features/events/lib/measurements` states
// the opposite rule for itself and the two agree — that one has a single
// reader.
//
// `domain-vocabulary/concepts/economics.yaml` NAMES THIS FILE as the console's
// consumer of `not_applicable_reason`, which is what makes the import below a
// declared fact rather than a convenience. The concept's other two consumers
// are the backend model that writes the value and the published contract that
// advertises it.

import { ABSENT_LABEL, labelMap } from "@/lib/localisation";
import {
  NOT_APPLICABLE_REASON_LABEL_KEYS,
  PRICING_STATUS_LABEL_KEYS,
  type NotApplicableReason,
  type PricingStatus,
} from "@/lib/vocabulary";

/** The catalogue's name for whether a customer price is settled. */
export const pricingStatusLabel = labelMap(PRICING_STATUS_LABEL_KEYS);

/** The catalogue's name for WHY a subject generates no customer revenue. */
export const notApplicableReasonLabel = labelMap(NOT_APPLICABLE_REASON_LABEL_KEYS);

// ⚠ NO `pricingMethodLabel` HERE YET, DELIBERATELY. `pricing_method` is the
// third concept whose value list this commit brings into `@/lib/labels` by
// reference, and the catalogue already carries both of its words under
// `pricing_method.*` — but nothing in the console renders a method today, and
// binding a label with no call site is a dead export a later reader has to
// classify. `costing_method` set that precedent and the adapter states it: *"a
// surface that comes to render one binds `labelMap(COSTING_METHOD_LABEL_KEYS)`
// in its own module."* #372 rebuilds the pricing feature and is where a method
// first reaches a screen — spec §21 gives it the case outright, two events of
// one Event Type reading differently because their receipts record different
// methods. `customer-price.test.ts` holds the catalogue to both words meanwhile,
// so the wording cannot rot while it waits.

/**
 * A posting's customer price, as any wire row or fixture carries it.
 *
 * Structural rather than a named response type, for the reason
 * `CostCompleteness` next door is: every surface spells the pair the same way,
 * so a caller passes the object it already holds and cannot pass an amount
 * without the status that says what it means. That is the same pairing rule
 * `@/lib/economic-scenarios` applies to a fixture, one layer up — the defect
 * both guard against is a call site that takes half.
 *
 * ⚠ THE AMOUNT IS OPTIONAL AND THE STATUS IS NOT, which is the wire's own
 * shape rather than a convenience. `pricing_status` is `required` on every
 * schema that publishes it and `billed_cost_micros` is not, so the generated
 * type makes the amount `number | null | undefined` — and a signature that
 * demanded it would push every call site into a `?? null` of its own, which is
 * one character from the coalesce this module exists to stop.
 *
 * The CAUSE rides along, optional, because the wire makes it optional: it is
 * read only under `not_applicable` and every schema publishing it is nullable.
 * One type rather than a base and an "explained" extension — with the field
 * optional, the extension enforced nothing at either call site and was three
 * shapes for one clump.
 */
export interface CustomerPrice {
  readonly billed_cost_micros?: number | null;
  readonly pricing_status: PricingStatus;
  readonly not_applicable_reason?: NotApplicableReason | null;
}

/**
 * The amount this price actually settled at, or `null` if it did not settle.
 *
 * ⚠ THE ONE PLACE THE STATUS IS READ, and every surface that shows a price —
 * or DERIVES a number from one — has to come through here rather than test the
 * column for null. `billed_cost_micros == null` is right for every row the
 * posting's own check constraint admits today, and it is right for the wrong
 * reason: the console is downstream of that constraint and renders whatever a
 * payload carries. A zero arriving beside `waived` is absent under this
 * question and `£0.00` under the column test — the status is the fact, the
 * amount is a consequence.
 *
 * ⚠ A MARGIN IS WHY THIS IS A FUNCTION AND NOT AN INLINE BRANCH. The event
 * receipt renders `billed − provider cost`, and a page that guarded the
 * displayed amount with the status while computing the margin off the raw
 * column would show a dash beside a real signed figure derived from the very
 * zero the dash exists to deny. That defect shipped in this module's first
 * draft and both review axes are the reason it did not survive it: the amount
 * had one guard and the number derived from it had none.
 */
export function settledPriceMicros(price: CustomerPrice): number | null {
  if (price.pricing_status !== "known") return null;
  return price.billed_cost_micros ?? null;
}

/**
 * A customer price, rendered so that an absence cannot be read as a charge of
 * nothing.
 *
 * The formatter is a parameter because the console formats money in more than
 * one precision: a single event's receipt keeps four decimals so a micro-priced
 * call never rounds to nothing, while a total does not. A module that fixed the
 * format would either pick one and be wrong somewhere, or grow a currency
 * argument it has no other use for.
 *
 * It renders the console's absent marker rather than the status word, because
 * its two callers put the status in a row of its own beside the amount. The
 * developer console's recorded response has no such row — it is a compact stat
 * grid — so it renders `pricingStatusLabel` in the cell itself, exactly as it
 * already does for the supplier cost. Both ask `settledPriceMicros` first.
 */
export function customerPriceAmount(
  price: CustomerPrice,
  format: (micros: number) => string,
): string {
  const micros = settledPriceMicros(price);
  return micros === null ? ABSENT_LABEL : format(micros);
}

/**
 * What each status means for the person reading a receipt.
 *
 * Total over the generated type and read by indexing rather than through a
 * lookup: a status the registry declares and this constant has no sentence for
 * is a `tsc` failure, which is the difference between console copy and a guess.
 * The same shape, and the same reasoning, as `COSTING_STATUS_EXPLANATIONS`.
 */
export const PRICING_STATUS_EXPLANATIONS = {
  known: "UBB resolved what to charge for this, and this is the amount.",
  unknown:
    "UBB has not resolved a customer price for this. The amount is missing rather than zero, and it is left out of every revenue total until it arrives.",
  waived:
    "Somebody decided not to pursue this charge. The revenue really is nothing — this is a decided loss rather than a question still open, so no total is a floor because of it.",
  not_applicable:
    "This subject generates no customer revenue at this level, so there is no price to resolve and nothing is missing from any total.",
} as const satisfies Record<PricingStatus, string>;

/**
 * Why a subject generates no customer revenue, in a sentence — and the two
 * sentences answer DIFFERENT questions.
 *
 * This is the pair the receipt has to keep apart. One says the revenue is real
 * and sits somewhere else, so there is a number to go and look at; the other
 * says no Charge was created anywhere, so there is not. A screen that gave both
 * the same words would answer "why is there no price here?" with a shrug in the
 * one case where UBB knows exactly why.
 *
 * ⚠ WHERE BOTH ARE TRUE, POSTURE WINS — the registry's own tie-break. A
 * metering-only tenant is `tenant_not_billing` whatever the job's pricing
 * regime, because naming the regime would imply revenue sits on a Charge that
 * does not exist. Nothing here decides that; the sentences are written so that
 * the value the server sent reads correctly on its own.
 */
export const NOT_APPLICABLE_REASON_EXPLANATIONS = {
  fixed_task_pricing:
    "This event belongs to a Task sold for one agreed price. The revenue is the Task's and none of it is this event's — the charge to look at is the Task's own.",
  tenant_not_billing:
    "This workspace meters usage and does not bill customers through UBB, so no customer charge exists anywhere and there is no price to look at.",
} as const satisfies Record<NotApplicableReason, string>;

/**
 * The one sentence to show beside a price, whichever of the five answers it is.
 *
 * The reason's sentence WINS where there is one, because the reason is the more
 * specific true thing: the registry reads `not_applicable_reason` only under
 * that status and says outright that a status saying a price does not apply
 * without saying why "sends a reader looking for a number nobody wrote".
 *
 * The status's own sentence is the fallback rather than the default, and the
 * case it covers is real rather than defensive: the reason is nullable on every
 * schema that publishes it, so a payload may legitimately arrive with the
 * status and no cause. Rendering nothing there would put the receipt back to a
 * dash with no explanation.
 */
export function customerPriceExplanation(price: CustomerPrice): string {
  const reason = price.not_applicable_reason;
  if (price.pricing_status === "not_applicable" && reason != null) {
    return NOT_APPLICABLE_REASON_EXPLANATIONS[reason];
  }
  return PRICING_STATUS_EXPLANATIONS[price.pricing_status];
}
