// The referral feature's words: a programme's reward type and status, a
// referral's status, and how a reward-ledger entry was worked out.
//
// Identity lives in `@/lib/vocabulary` (generated from `domain-vocabulary/`),
// expression in `@/locales` reached through `@/lib/localisation` — the
// `@/lib/products` pattern. Declared in R10-W4 (slice 8), which deleted the
// hand-written map in `@/lib/labels` this replaces; that map fell back to the
// humaniser, which ADR-0008 §4.3 calls a defect. The registry names this file
// as the console's consumer of the concept(s) below.
//
// The programme map lacked `paused` and rendered it through the humaniser; a
// referral's status and a ledger entry's calculation method were humanised
// outright (`g6-humanises-referrals-table`, `-attribute-referral-dialog`,
// `-ledger-dialog`). Every value now has the catalogue's word.

import { labelMap } from "@/lib/localisation";
import {
  CALCULATION_METHOD_LABEL_KEYS,
  REFERRAL_PROGRAM_STATUS_LABEL_KEYS,
  REFERRAL_STATUS_LABEL_KEYS,
  REWARD_TYPE_LABEL_KEYS,
} from "@/lib/vocabulary";

/** The catalogue's words for a programme's reward type. */
export const rewardTypeLabel = labelMap(REWARD_TYPE_LABEL_KEYS);

/** The catalogue's words for a programme's status. */
export const referralProgramStatusLabel = labelMap(REFERRAL_PROGRAM_STATUS_LABEL_KEYS);

/** The catalogue's words for a referral's status. */
export const referralStatusLabel = labelMap(REFERRAL_STATUS_LABEL_KEYS);

/** The catalogue's words for how a reward-ledger entry was calculated. */
export const calculationMethodLabel = labelMap(CALCULATION_METHOD_LABEL_KEYS);
