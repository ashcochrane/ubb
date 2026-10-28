// The tenant's real-time spend-control switch: the registry's words.
//
// Identity lives in `@/lib/vocabulary` (generated from `domain-vocabulary/`),
// expression in `@/locales` reached through `@/lib/localisation` — the
// `@/lib/products` pattern. Declared in R10-W4 (slice 8), which deleted the
// hand-written map in `@/lib/labels` this replaces; that map fell back to the
// humaniser, which ADR-0008 §4.3 calls a defect. The registry names this file
// as the console's consumer of the concept(s) below.
//
// It sits in `lib/` because the Spend controls page shows the posture and the
// settings card changes it.

import { labelMap } from "@/lib/localisation";
import {
  ENFORCEMENT_MODE_LABEL_KEYS,
  ENFORCEMENT_MODE_VALUES,
} from "@/lib/vocabulary";

/** The catalogue's words for the tenant's enforcement mode. */
export const enforcementModeLabel = labelMap(ENFORCEMENT_MODE_LABEL_KEYS);

/** Both modes, held by reference — what the settings card offers. */
export const ENFORCEMENT_MODES = ENFORCEMENT_MODE_VALUES;
