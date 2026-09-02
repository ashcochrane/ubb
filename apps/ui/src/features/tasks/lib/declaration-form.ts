// The declare-a-kind-of-work form: its schema, and the conversions between
// what a person types and what the registry takes. Number-bearing fields stay
// strings in form state (partial input never fights the user) and become
// integers exactly once, at submit.

import { z } from "zod";

import { PRICING_MODE_VALUES, TASK_TYPE_KIND_VALUES } from "@/lib/vocabulary";

import type { KindOfWork, KindOfWorkDeclaration } from "../api/types";

const AMOUNT = /^\d+(\.\d{1,6})?$/;
const WHOLE_SECONDS = /^\d+$/;

// ⚠ THE TWO VALUE SETS COME FROM THE GENERATED VOCABULARY, never typed here:
// a schema that listed the two regimes itself would be a second copy of a set
// the registry owns, which is the drift the consumer gates exist to abolish.
export const kindFormSchema = z.object({
  key: z
    .string()
    .trim()
    .min(1, "Required")
    .max(64, "Keep the key under 64 characters")
    .regex(/^[A-Za-z0-9_-]+$/, "Letters, digits, hyphens and underscores only"),
  kind: z.enum(TASK_TYPE_KIND_VALUES),
  pricing_mode: z.enum(PRICING_MODE_VALUES),
  ceiling: z
    .string()
    .trim()
    .refine((value) => value === "" || (AMOUNT.test(value) && Number(value) > 0), {
      message: "An amount above zero, or leave it empty to use the workspace default.",
    }),
  silence_window_seconds: z
    .string()
    .trim()
    .refine((value) => value === "" || WHOLE_SECONDS.test(value), {
      message: "Whole seconds, or leave it empty to use the workspace default.",
    }),
  absolute_deadline_seconds: z
    .string()
    .trim()
    .refine((value) => value === "" || (WHOLE_SECONDS.test(value) && Number(value) > 0), {
      message: "Whole seconds above zero, or leave it empty for no deadline.",
    }),
});

export type KindFormValues = z.infer<typeof kindFormSchema>;

/**
 * The same form on a REVISION, where the key is not in play.
 *
 * The key control is disabled and its value comes off the standing row, so
 * the grammar above — a console-side nicety for a key being minted — must not
 * run against it: the wire accepts any string, and a kind declared from the
 * API under a spelling this form would refuse must still be revisable here.
 */
export const revisionFormSchema = kindFormSchema.extend({ key: z.string() });

/** An amount in the workspace currency, as typed, to integer micros; empty is none. */
export function amountToMicros(value: string): number | null {
  const trimmed = value.trim();
  return trimmed === "" ? null : Math.round(Number(trimmed) * 1_000_000);
}

/** Integer micros back to the amount a person would type; none is empty. */
export function microsToAmount(micros: number | null | undefined): string {
  return micros == null ? "" : (micros / 1_000_000).toString();
}

function secondsToField(seconds: number | null | undefined): string {
  return seconds == null ? "" : String(seconds);
}

function fieldToSeconds(value: string): number | null {
  const trimmed = value.trim();
  return trimmed === "" ? null : Number(trimmed);
}

/** What the form opens holding: the standing declaration, or a blank one. */
export function formDefaults(existing?: KindOfWork): KindFormValues {
  if (existing === undefined) {
    return {
      key: "",
      kind: "task",
      pricing_mode: "event_priced",
      ceiling: "",
      silence_window_seconds: "",
      absolute_deadline_seconds: "",
    };
  }
  return {
    key: existing.key,
    kind: existing.kind,
    pricing_mode: existing.pricing_mode,
    ceiling: microsToAmount(existing.default_provider_cost_limit_micros),
    silence_window_seconds: secondsToField(existing.silence_window_seconds),
    absolute_deadline_seconds: secondsToField(existing.absolute_deadline_seconds),
  };
}

/**
 * The declaration the form states.
 *
 * ⚠ FOR A STANDING KIND, THE IDENTITY AND THE REGIME COME FROM THE ROW, NOT
 * THE FORM. Both controls are disabled on a revision — the key and the
 * altitude are the declaration's identity, and the regime is FROZEN (#187
 * §10) — and a disabled control's value is not something to build a money
 * declaration on. Reading them off the standing row is what makes "the regime
 * control is disabled" a true statement about the wire and not only about the
 * screen.
 *
 * Required grouping fields are not on this form: a revision keeps the standing
 * set and a new kind starts with none.
 */
export function toDeclaration(
  values: KindFormValues,
  existing?: KindOfWork,
): KindOfWorkDeclaration {
  return {
    key: existing?.key ?? values.key,
    kind: existing?.kind ?? values.kind,
    pricing_mode: existing?.pricing_mode ?? values.pricing_mode,
    default_provider_cost_limit_micros: amountToMicros(values.ceiling),
    silence_window_seconds: fieldToSeconds(values.silence_window_seconds),
    absolute_deadline_seconds: fieldToSeconds(values.absolute_deadline_seconds),
    required_dimensions: existing ? [...existing.required_dimensions] : [],
    retired: existing?.retired ?? false,
  };
}
