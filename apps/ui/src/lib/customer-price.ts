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
//     unknown         information UBB does not have — left out of every total
//                     and counted among the amounts not included; a recovery
//                     run revisits it, unless a `pricing_status_reason` says
//                     why UBB cannot carry the price it calculated (#603)
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
// consumer of `not_applicable_reason` and of `pricing_status_reason`, which is
// what makes the imports below a declared fact rather than a convenience. The concept's other two consumers
// are the backend model that writes the value and the published contract that
// advertises it.

import { ABSENT_LABEL, labelMap } from "@/lib/localisation";
import {
  NOT_APPLICABLE_REASON_LABEL_KEYS,
  PRICING_METHOD_LABEL_KEYS,
  PRICING_STATUS_LABEL_KEYS,
  PRICING_STATUS_REASON_LABEL_KEYS,
  type NotApplicableReason,
  type PricingStatus,
  type PricingStatusReason,
} from "@/lib/vocabulary";

/** The catalogue's name for whether a customer price is settled. */
export const pricingStatusLabel = labelMap(PRICING_STATUS_LABEL_KEYS);

/** The catalogue's name for WHY a subject generates no customer revenue. */
export const notApplicableReasonLabel = labelMap(NOT_APPLICABLE_REASON_LABEL_KEYS);

/**
 * The catalogue's name for WHY a pricing status applies, where a published
 * reason does (#603): today, only why an `unknown` price is one UBB
 * calculated and cannot carry.
 */
export const pricingStatusReasonLabel = labelMap(PRICING_STATUS_REASON_LABEL_KEYS);

/**
 * A price's status in the catalogue's words, WITH its own reason where one
 * was published (#603): "Unknown · Negative price not carried", or the
 * status's word alone. The one spelling for every surface that shows a
 * pricing status, so no surface shows an `unknown` and drops the reason that
 * says it will never resolve.
 */
export function pricingStatusWords(
  price: Pick<CustomerPrice, "pricing_status" | "pricing_status_reason">,
): string {
  const status = pricingStatusLabel(price.pricing_status);
  return price.pricing_status_reason == null
    ? status
    : `${status} · ${pricingStatusReasonLabel(price.pricing_status_reason)}`;
}

/**
 * The catalogue's name for HOW a customer price was derived.
 *
 * ⚠ **THIS IS THE BINDING #371 DELIBERATELY DID NOT MAKE, AND IT LANDS HERE
 * RATHER THAN IN THE PRICING FEATURE.** That commit brought `pricing_method`'s
 * value list into `@/lib/labels` by reference and stopped, on the
 * `costing_method` precedent: *"a surface that comes to render one binds
 * `labelMap(...)` in its own module"*, because a label with no call site is a
 * dead export a later reader has to classify. #372 is that surface — and it
 * turns out to be TWO surfaces, which is what decides the home. The pricing
 * feature renders a method on its rules and in a publish's diff; the events
 * feature renders it on the receipt, because spec §21 asks outright for two
 * events of one Event Type to read differently when their receipts record
 * different methods. The console's imports only flow down and one feature never
 * reaches into another, so a concept two features render binds in `lib/` — the
 * rule this module's own header states about itself.
 *
 * ⚠ **AND IT IS A DIFFERENT FACT FROM `rate_structure`**, which stays inside
 * the pricing feature because the rules table is its only reader. One says
 * where a number came from; the other says how a quantity multiplies out. They
 * are a near miss in a reader's head rather than in the code, and a rule may
 * move either without the other.
 */
export const pricingMethodLabel = labelMap(PRICING_METHOD_LABEL_KEYS);

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
 *
 * ⚠ THE STATUS'S OWN REASON IS REQUIRED, because the wire makes it required:
 * `pricing_status_reason` is published REQUIRED AND NULLABLE wherever
 * `pricing_status` is (#603), so a row that dropped it would be a row the
 * server never sent.
 */
export interface CustomerPrice {
  readonly billed_cost_micros?: number | null;
  readonly pricing_status: PricingStatus;
  readonly pricing_status_reason: PricingStatusReason | null;
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
  // REASON-NEUTRAL, ON PURPOSE (#603; the owner's review of #614): an
  // `unknown` price may be one UBB could not determine OR one it calculated
  // exactly and will not publish (`negative_price_unsupported`), and the
  // second is not "missing". What separates the two is the reason's own
  // sentence, which `customerPriceExplanation` adds after this one.
  unknown:
    "No authoritative customer price is recorded for this event. It is not treated as zero and is not included in revenue totals.",
  waived:
    "Somebody decided not to pursue this charge. The revenue really is nothing — this is a decided loss rather than a question still open, so no total is missing it.",
  not_applicable:
    "This subject generates no customer revenue at this level, so there is no price to resolve and nothing is missing from any total.",
} as const satisfies Record<PricingStatus, string>;

/**
 * Why a subject generates no customer revenue, in a sentence.
 *
 * The revenue is real and sits somewhere else, so there is a number to go and
 * look at: the Task's own charge. It is the answer for every workspace (#553):
 * the regime decides the reason, and whether the workspace bills through UBB
 * is not encoded again here. The posture value that once sat beside it was
 * removed with its last producer; a value the server sends that the catalogue
 * no longer words renders as the token it is (`@/lib/localisation`), never as
 * this sentence.
 */
export const NOT_APPLICABLE_REASON_EXPLANATIONS = {
  fixed_task_pricing:
    "This event belongs to a Task sold for one agreed price. The revenue is the Task's and none of it is this event's — the charge to look at is the Task's own.",
} as const satisfies Record<NotApplicableReason, string>;

/**
 * Why an `unknown` price is unknown, where the server published a reason, in
 * the sentence that follows the status's own (#603). Total over the generated
 * type, as the two maps above are.
 */
export const PRICING_STATUS_REASON_EXPLANATIONS = {
  event_type_not_declared:
    "The event names an Event Type nobody has published, so nothing says what the call was. It is held until the Event Type is published or the name is mapped, then priced as of when it happened.",
  measurement_not_declared:
    "The event carries a quantity its Event Type's publication does not declare, so nothing says what it measures. It is held until the name is declared or mapped, then priced as of when it happened.",
  negative_price_unsupported:
    "UBB calculated a negative price, but the current money rails cannot carry it authoritatively. Nothing was clamped to zero or charged, and no recovery run will resolve it.",
} as const satisfies Record<PricingStatusReason, string>;

/**
 * The same sentence where the server published NO reason — the ordinary
 * `unknown`, for want of input. The reason is nullable on every schema that
 * publishes it, and null means no specific published reason applies, which
 * for this status is a price that could not be determined.
 */
export const UNKNOWN_PRICE_WITHOUT_A_REASON =
  "The price could not be determined from the configuration and inputs UBB had; a resolution run can complete it once they are in place.";

/**
 * The one sentence to show beside a price, whichever of the answers it is.
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
 *
 * ⚠ `unknown` IS THE EXCEPTION: ITS SENTENCE IS TWO, AND NEITHER WINS (#603;
 * the owner's review of #614). The status's own sentence is reason-neutral —
 * no authoritative price is recorded, it is not zero, it is not in revenue —
 * and the reason's sentence follows it: a negative price UBB calculated and
 * the rails cannot carry, or, where the server published no reason, a price
 * that could not be determined. Collapsing the two meanings into one sentence
 * is what `pricing_status_reason` exists to prevent.
 */
export function customerPriceExplanation(price: CustomerPrice): string {
  const reason = price.not_applicable_reason;
  if (price.pricing_status === "not_applicable" && reason != null) {
    return NOT_APPLICABLE_REASON_EXPLANATIONS[reason];
  }
  if (price.pricing_status === "unknown") {
    const why = price.pricing_status_reason === null
      ? UNKNOWN_PRICE_WITHOUT_A_REASON
      : PRICING_STATUS_REASON_EXPLANATIONS[price.pricing_status_reason];
    return `${PRICING_STATUS_EXPLANATIONS.unknown} ${why}`;
  }
  return PRICING_STATUS_EXPLANATIONS[price.pricing_status];
}
