// What a stop applies to: the registry's words for a stop scope.
//
// Identity lives in `@/lib/vocabulary` (generated from `domain-vocabulary/`),
// expression in `@/locales` reached through `@/lib/localisation` — the
// `@/lib/products` pattern. Declared in R10-W4 (slice 8), which deleted the
// hand-written map in `@/lib/labels` this replaces; that map fell back to the
// humaniser, which ADR-0008 §4.3 calls a defect. The registry names this file
// as the console's consumer of the concept(s) below.
//
// It sits in `lib/` because the events feature (the stop-context timeline and
// the event filters) and the developers feature (a Verify acknowledgement)
// both render one.

import { labelMap } from "@/lib/localisation";
import { STOP_SCOPE_LABEL_KEYS, STOP_SCOPE_VALUES } from "@/lib/vocabulary";

/** The catalogue's words for a stop scope. */
export const stopScopeLabel = labelMap(STOP_SCOPE_LABEL_KEYS);

/** The three scopes, held by reference — what a filter offers. */
export const STOP_SCOPES = STOP_SCOPE_VALUES;
