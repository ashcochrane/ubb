// A credit grant's kind, status and source: the registry's words.
//
// Identity lives in `@/lib/vocabulary` (generated from `domain-vocabulary/`),
// expression in `@/locales` reached through `@/lib/localisation` — the
// `@/lib/products` pattern. Declared in R10-W4 (slice 8), which deleted the
// hand-written map in `@/lib/labels` this replaces; that map fell back to the
// humaniser, which ADR-0008 §4.3 calls a defect. The registry names this file
// as the console's consumer of the concept(s) below.

import { labelMap } from "@/lib/localisation";
import {
  GRANT_KIND_LABEL_KEYS,
  GRANT_SOURCE_LABEL_KEYS,
  GRANT_STATUS_LABEL_KEYS,
} from "@/lib/vocabulary";

/** The catalogue's words for a grant's kind. */
export const grantKindLabel = labelMap(GRANT_KIND_LABEL_KEYS);

/** The catalogue's words for a grant's status. */
export const grantStatusLabel = labelMap(GRANT_STATUS_LABEL_KEYS);

/** The catalogue's words for where a grant came from. */
export const grantSourceLabel = labelMap(GRANT_SOURCE_LABEL_KEYS);
