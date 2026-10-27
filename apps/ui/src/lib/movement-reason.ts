// Why money moved through a wallet by hand: the registry's words for it (#479).
//
// Identity lives in `@/lib/vocabulary` (generated from `domain-vocabulary/`),
// expression in `@/locales` reached through `@/lib/localisation` — the
// `@/lib/billing-mode` pattern. It sits in `lib/` because two features ask an
// operator for one: the billing credit/debit forms, and a customer's adjust
// dialogs. The field was `reason_code` until #479; that is the stop cause's
// name, a different concept, and the console renders that one elsewhere.

import { z } from "zod";

import { labelMap } from "@/lib/localisation";
import {
  MOVEMENT_REASON_LABEL_KEYS,
  MOVEMENT_REASON_VALUES,
  type MovementReason,
} from "@/lib/vocabulary";

/** The catalogue's words for a movement reason; the raw token for an unfamiliar one. */
export const movementReasonLabel = labelMap(MOVEMENT_REASON_LABEL_KEYS);

/** Every reason an operator may give, held by reference from the registry. */
export const MOVEMENT_REASONS = MOVEMENT_REASON_VALUES;

/** A form's reason field: one of the registry's six, or "" for none given. */
export const movementReasonField = z.union([
  z.literal(""),
  z.enum(MOVEMENT_REASON_VALUES),
]);

/** What the request sends for a form's reason: the reason, or null for none. */
export function movementReasonToSend(
  value: "" | MovementReason,
): MovementReason | null {
  return value === "" ? null : value;
}
