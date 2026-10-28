// Where a team member's seat and an invitation stand: the registry's words.
//
// Identity lives in `@/lib/vocabulary` (generated from `domain-vocabulary/`),
// expression in `@/locales` reached through `@/lib/localisation` — the
// `@/lib/products` pattern. Declared in R10-W4 (slice 8), which deleted the
// hand-written map in `@/lib/labels` this replaces; that map fell back to the
// humaniser, which ADR-0008 §4.3 calls a defect. The registry names this file
// as the console's consumer of the concept(s) below.

import { labelMap } from "@/lib/localisation";
import {
  INVITATION_STATUS_LABEL_KEYS,
  MEMBER_STATUS_LABEL_KEYS,
} from "@/lib/vocabulary";

/** The catalogue's words for a member's status. */
export const memberStatusLabel = labelMap(MEMBER_STATUS_LABEL_KEYS);

/** The catalogue's words for an invitation's status. */
export const invitationStatusLabel = labelMap(INVITATION_STATUS_LABEL_KEYS);
