// A run's ceiling assessment, as this feature reads and words it (#454;
// slice 6 §3, §18).
//
// THE STATUS IS READ, NEVER DERIVED. The kernel concludes one of the
// registry's four values on the row (`core/crossing.py`, the decision rule
// `spend-controls.yaml` carries as data) and publishes it beside two figures
// computed over the KNOWN total; the console renders what arrived. Nothing
// here compares a total to a ceiling, and no renderer may: the compare lives
// in the kernel, and the one console copy of its rule is the scenario
// composer's refusal of a fixture the rule contradicts
// (`@/lib/economic-scenarios`), which composes rows and renders nothing.
//
// THE WORDS ARE BOUND HERE because the run page is the only surface that
// renders them. `@/lib/task-status` sits a layer down for the reason it
// states — two features render a lifecycle state — and the day the
// Utilisation and headroom report (slice 6 §14, its own feature) renders a
// ceiling status too, this binding moves to `@/lib/` the way
// `@/lib/pricing-mode` did in #425. Identity is the registry's
// (`@/lib/vocabulary`), expression the catalogue's (`@/locales`, through
// `@/lib/localisation`), and the sentences beside them are the console's own
// (ADR-0008 §4.5).
//
// WHAT EACH STATUS IS NOT, because the renderings a naive reader would
// collapse are the ones this slice exists to keep apart (Testing Decisions
// claim 15): `not_applicable` is nothing evaluated — never "within", never
// "indeterminate", and its two figures are null, so no share and no `$0.00`
// renders for it; `indeterminate` is UBB having tried and been unable to
// tell — its percentage is a floor and its headroom a most, said as "at
// least" / "at most" and never as "under" anything; `ceiling_reached` was
// concluded on the known total alone and no later resolution softens it.

import { formatMicros } from "@/lib/format";
import { labelMap } from "@/lib/localisation";
import { AT_LEAST, AT_MOST } from "@/lib/supplier-cost";
import { CEILING_STATUS_LABEL_KEYS, type CeilingStatus } from "@/lib/vocabulary";

import { eventsHave } from "./runs";

/** The catalogue's words for what the assessment concluded; the raw token for an unfamiliar one. */
export const ceilingStatusLabel = labelMap(CEILING_STATUS_LABEL_KEYS);

/**
 * Any row carrying the assessment beside the columns it was concluded from —
 * the shape both unit reads publish (`TaskOut`, `TaskDetailOut`). The pinned
 * ceiling and the two figures are optional-nullable on the generated type
 * because the schema does not list them as required; the status and the
 * unresolved count it does, so they are always sent.
 */
export interface CeilingAssessed {
  readonly task_cogs_ceiling_micros?: number | null;
  readonly ceiling_status: CeilingStatus;
  readonly ceiling_used_percentage?: number | null;
  readonly ceiling_remaining_micros?: number | null;
  readonly unresolved_event_count: number;
}

/**
 * What the assessment concluded, and — where something was evaluated — the
 * figures it was concluded over.
 *
 * A union keyed on the status, so a renderer branches on WHICH conclusion it
 * holds and cannot coalesce the nothing-evaluated case into a number. The
 * evaluated arm keeps each figure nullable rather than defaulting it: the
 * percentage is null on the wire for a ceiling of zero (a share of nothing
 * is not a share), and a reader that wrote `?? 0` there would render exactly
 * the confident number this surface must not.
 */
export type CeilingReading =
  | { readonly kind: "not_applicable" }
  | {
      readonly kind: Exclude<CeilingStatus, "not_applicable">;
      readonly ceilingMicros: number | null;
      readonly usedPercentage: number | null;
      readonly remainingMicros: number | null;
      /** How many events' supplier cost the known total could not include. */
      readonly eventsLeftOut: number;
    };

export function readCeiling(row: CeilingAssessed): CeilingReading {
  if (row.ceiling_status === "not_applicable") return { kind: "not_applicable" };
  return {
    kind: row.ceiling_status,
    ceilingMicros: row.task_cogs_ceiling_micros ?? null,
    usedPercentage: row.ceiling_used_percentage ?? null,
    remainingMicros: row.ceiling_remaining_micros ?? null,
    eventsLeftOut: row.unresolved_event_count,
  };
}

/**
 * The figures beside the status — the ceiling, the share of it used, the
 * headroom left — or nothing where nothing was evaluated.
 *
 * Under `indeterminate` the share is "at least" and the headroom "at most",
 * because both are over the known total and unresolved costs can only move
 * them one way. Each figure renders only where the wire sent one: a null is
 * left out, never written as zero.
 */
export function describeCeilingFigures(reading: CeilingReading, currency: string): string | null {
  if (reading.kind === "not_applicable") return null;
  const floor = reading.kind === "indeterminate";
  const parts: string[] = [];
  if (reading.ceilingMicros !== null) {
    parts.push(`${formatMicros(reading.ceilingMicros, currency)} ceiling`);
  }
  if (reading.usedPercentage !== null) {
    parts.push(`${floor ? `${AT_LEAST} ` : ""}${reading.usedPercentage}% used`);
  }
  if (reading.remainingMicros !== null) {
    parts.push(`${floor ? `${AT_MOST} ` : ""}${formatMicros(reading.remainingMicros, currency)} headroom`);
  }
  return parts.length === 0 ? null : parts.join(" · ");
}

/**
 * What each conclusion means for the person reading a run — console-owned
 * copy (ADR-0008 §4.5), total over the generated type so a status the
 * registry adds and this has no sentence for fails `tsc` rather than
 * rendering nothing. The `not_applicable` sentence names both causes because
 * the wire does not say which applies (#453, slice 6 Out of Scope); the
 * `indeterminate` sentence avoids "under" on purpose (see the module header).
 */
export const CEILING_STATUS_EXPLANATIONS = {
  not_applicable:
    "No ceiling applies to this run: its kind is declared uncapped, or nothing declares one. Nothing was evaluated, so nothing was concluded.",
  within_ceiling:
    "Every supplier cost this run has reported is known, and their total is below the ceiling.",
  indeterminate:
    "UBB cannot prove this run is inside its ceiling. The figures are over what is known: the share used can only rise and the headroom only fall as the rest settles.",
  ceiling_reached:
    "The known supplier cost has reached the ceiling. Costs still unresolved can only add to it, so no later resolution softens this.",
} as const satisfies Record<CeilingStatus, string>;

/** The sentence beside a ceiling reading, with the count of what the known total left out where that count is what the reading turns on. */
export function explainCeiling(reading: CeilingReading): string {
  const explanation = CEILING_STATUS_EXPLANATIONS[reading.kind];
  if (reading.kind === "not_applicable" || reading.eventsLeftOut === 0) return explanation;
  return `${eventsHave(reading.eventsLeftOut)} a supplier cost UBB has not learned. ${explanation}`;
}
