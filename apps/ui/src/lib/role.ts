// A tenant principal's role: the registry's words, and the rank a floor
// compares by.
//
// Identity lives in `@/lib/vocabulary` (generated from `domain-vocabulary/`),
// expression in `@/locales` reached through `@/lib/localisation` — the
// `@/lib/products` pattern. Declared in R10-W4 (slice 8), which deleted the
// hand-written map in `@/lib/labels` this replaces; that map fell back to the
// humaniser, which ADR-0008 §4.3 calls a defect. The registry names this file
// as the console's consumer of the concept(s) below.
//
// It sits in `lib/` because the shell's account menu and the settings feature
// both render a role. The rank is the registry's declared order, lowest first,
// so the console cannot keep a second opinion of which role outranks which.

import { labelMap } from "@/lib/localisation";
import { ROLE_LABEL_KEYS, ROLE_VALUES, type Role } from "@/lib/vocabulary";

/** The catalogue's words for a role; the raw token for an unfamiliar one. */
export const roleLabel = labelMap(ROLE_LABEL_KEYS);

/** Every role, lowest authority first — the order a picker offers them in. */
export const ROLES: readonly Role[] = ROLE_VALUES;

/** Rank a role for floor comparisons; an unknown role ranks lowest (fail closed). */
export function roleRank(role: string | null | undefined): number {
  return ROLE_VALUES.indexOf(role as Role);
}
