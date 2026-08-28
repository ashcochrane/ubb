// The Pricing Receipt's per-quantity component, as the engine writes it.
//
// ⚠ **WHY THIS IS ITS OWN MODULE, AND IT IS NOT A STYLE CHOICE.** The record's
// key for "how much of this quantity was priced" is a word slice 2 retired as a
// SENSE — the usage row's own nameless total — while the sense inside a receipt
// SURVIVES: #366 ruled the key stays, because re-spelling it would be a change
// to the shape of a stored record with no ticket behind it. The two senses are
// one token, so `tests/contracts/test_the_inline_unit_total_is_gone.py` cannot
// tell them apart by reading: it names the seventeen files that read the
// RETIRED one and forbids the word there outright, comments included, and says
// in its own docstring that every other file in the tree is free to say it.
//
// `features/events/api/mock-data.ts` is on that list. So the word lives here,
// once, and the fixtures beside it say what they mean — which is Phase B's
// second technique. `correlationIds` in that file was written for exactly this
// trade over a different retired word; #411 deleted that word's field, so the
// helper survives as `correlationId` on a weaker argument and this module is
// now the only place in the feature making the trade for a live debt.
//
// ⚠ **AND THE CALLER'S WORD FOR THE QUANTITY IS `quantity`**, which is the name
// the engine's own builder takes (`pricing_service._component(measurement_key,
// quantity, card)`). It is not a euphemism invented to dodge a gate: the
// parameter really is called that upstream, and the record's key is the only
// place the other spelling belongs.

/**
 * One line of an explanation: the quantity, the rule's terms, and the amount.
 *
 * ⚠ **THE RECEIPT HAS TO OUTLIVE THE MEASUREMENTS IT EXPLAINS.** The detailed
 * measurement rows are a child record with a retention horizon of their own and
 * the receipt is kept for six years, so a component recording only a quantity
 * and a total would explain nothing the day the detail expires. Every term the
 * arithmetic used is written down BY VALUE — and the denominator is not
 * decoration: a rate is "so much per N", and a component holding the rate
 * without the N cannot be recomputed at all.
 *
 * One shape for both sections, because a cost component and a price component
 * are the same fact about different rules — and two spellings of one shape is
 * how the two come to differ exactly where a reader compares them.
 */
export interface ReceiptComponent {
  readonly measurement_key: string;
  readonly units: number;
  readonly rate_structure: string;
  readonly rate_per_unit_micros: number;
  readonly unit_quantity: number;
  readonly fixed_micros: number;
  readonly micros: number;
}

/** Build one, from the terms a fixture states. */
export function receiptComponent(terms: {
  measurement_key: string;
  quantity: number;
  rate_per_unit_micros: number;
  unit_quantity: number;
  micros: number;
  rate_structure?: string;
  fixed_micros?: number;
}): ReceiptComponent {
  return {
    measurement_key: terms.measurement_key,
    units: terms.quantity,
    rate_structure: terms.rate_structure ?? "per_unit",
    rate_per_unit_micros: terms.rate_per_unit_micros,
    unit_quantity: terms.unit_quantity,
    fixed_micros: terms.fixed_micros ?? 0,
    micros: terms.micros,
  };
}
