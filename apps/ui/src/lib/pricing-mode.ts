// The words for how a kind of work is sold — `pricing_mode`, bound once.
//
// Identity is the registry's (`@/lib/vocabulary`), expression the catalogue's
// (`@/locales`, reached through `@/lib/localisation`): the split `@/lib/products`
// makes, and for the same reason. #423 bound this inside the tasks feature,
// the surface that renders a kind of work; #425 moved it here because a second
// feature now renders the same word — the events feature, on the receipt of a
// charge, which carries the regime BY VALUE (`pricing.detail.pricing_mode`) so
// that the record says the price was agreed rather than derived. The console's
// imports only flow down and one feature never reaches into another, so a
// concept two features render binds in `lib/` — the rule `@/lib/customer-price`
// states for `pricing_method`, applied a second time.
//
// The console-owned sentences about each regime stay where they were:
// `features/tasks/lib/kinds.ts` explains a regime to somebody declaring one,
// and nothing else needs those words.

import { labelMap } from "@/lib/localisation";
import { PRICING_MODE_LABEL_KEYS } from "@/lib/vocabulary";

/** The catalogue's words for how a kind of work is sold. */
export const pricingModeLabel = labelMap(PRICING_MODE_LABEL_KEYS);
