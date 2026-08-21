// What a rate's arithmetic shape is called (#371).
//
// Identity is the registry's (`@/lib/vocabulary`), expression the catalogue's
// (`@/locales`, reached through `@/lib/localisation`) — the split
// `@/lib/products` and `features/events/lib/measurements` both make, and the
// one `@/lib/labels` is being emptied into.
//
// It replaces a hand-written map in `@/lib/labels` that spelled "Per unit" and
// "Fixed component" in English beside the values and fell back to the humaniser
// for anything else. The catalogue already carried both of those words under
// `rate_structure.*`, so this is the same wording read from the place that owns
// it rather than a second copy — and a value the registry adds tomorrow gets
// its word from the catalogue instead of a title-cased guess.
//
// THIS LIVES IN THE PRICING FEATURE rather than in `lib/` because the rates
// table is its only reader. `@/lib/customer-price` states the opposite rule for
// itself and the two agree: that one is read by two features that cannot share
// one, this one by a table three files away.
//
// ⚠ "Structure" MEANS THE MATHEMATICAL SHAPE AND NOTHING ELSE (ADR-0006 §3).
// It is not the regime a job is sold under and it is not how a price was
// derived — those are `pricing_mode` and `pricing_method`, two other concepts
// with two other label prefixes. The names are close enough that a reader
// reaching for "the pricing model" lands on the wrong one, which is exactly
// what the map this replaces was called.

import { labelMap } from "@/lib/localisation";
import { RATE_STRUCTURE_LABEL_KEYS } from "@/lib/vocabulary";

/** The catalogue's name for a rate's arithmetic shape. */
export const rateStructureLabel = labelMap(RATE_STRUCTURE_LABEL_KEYS);
