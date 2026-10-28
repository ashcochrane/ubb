// The audit feed's words: what was done, to which kind of record, and by whom.
//
// Identity lives in `@/lib/vocabulary` (generated from `domain-vocabulary/`),
// expression in `@/locales` reached through `@/lib/localisation` — the
// `@/lib/products` pattern. Declared in R10-W4 (slice 8), which deleted the
// hand-written map in `@/lib/labels` this replaces; that map fell back to the
// humaniser, which ADR-0008 §4.3 calls a defect. The registry names this file
// as the console's consumer of the concept(s) below.
//
// The action was worded by splitting it on the dot and humanising both halves
// (`g6-humanises-settings`), and the resource type by humanising it
// (`g6-humanises-audit-log-page`); both are the catalogue's words now. Who
// acted is an OPEN concept (ADR-004 §4), so the feed renders it through
// `components/shared/open-set-value.tsx` with the label keys below: a kind
// the console has never met renders as the token it is, marked, never guessed.

import { labelMap } from "@/lib/localisation";
import {
  ACTOR_KIND_LABEL_KEYS,
  AUDIT_ACTION_LABEL_KEYS,
  AUDIT_RESOURCE_TYPE_LABEL_KEYS,
} from "@/lib/vocabulary";

/** The catalogue's words for an audited action. */
export const auditActionLabel = labelMap(AUDIT_ACTION_LABEL_KEYS);

/** The catalogue's words for the kind of record an action changed. */
export const auditResourceTypeLabel = labelMap(AUDIT_RESOURCE_TYPE_LABEL_KEYS);

/** Who acted — handed to `OpenSetValue`, which owns the open-set rule. */
export const ACTOR_KIND_LABELS = ACTOR_KIND_LABEL_KEYS;
