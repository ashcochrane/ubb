// A kind of work, as this feature reasons about one: what a tenant is told
// when declaring it, the ceiling it really runs under, and the price its runs
// were quoted.
//
// THE WORDS FOR `pricing_mode` WERE BOUND HERE BY #423 AND MOVED TO
// `@/lib/pricing-mode` BY #425, the day a second feature came to render the
// same word: the events feature shows the regime a charge's receipt carries
// by value, and one feature never reaches into another. The registry names
// `@/lib/labels` as the console's consumer of the value list, and that file
// holds the list by reference and nothing else — the legacy adapter is not
// where a migrated concept's wording lives. What stays here is the copy only
// this surface needs: what each regime means to somebody declaring one.

import type { TenantConfig } from "@/hooks/use-tenant-config";
import { formatMicros, formatPercent } from "@/lib/format";
import { ABSENT_LABEL, labelMap } from "@/lib/localisation";
import { TASK_TYPE_KIND_LABEL_KEYS, type PricingMode } from "@/lib/vocabulary";

import {
  sameDeclaration,
  type DeclareKindsBody,
  type KindOfWork,
  type KindOfWorkDeclaration,
  type RunRow,
} from "../api/types";

/** The catalogue's words for which altitude a declaration is meant for. */
export const altitudeLabel = labelMap(TASK_TYPE_KIND_LABEL_KEYS);

/**
 * What each regime does, in a sentence — console-owned copy (ADR-0008 §4.5),
 * total over the generated type so a regime the registry adds and this has no
 * sentence for fails `tsc` rather than rendering nothing.
 */
export const PRICING_MODE_EXPLANATIONS = {
  event_priced:
    "Every event under a run is priced as it arrives, from the rules in the pricing book.",
  fixed:
    "A delivered run is charged one agreed price from the pricing book. The events under it are still costed, but none of them is priced.",
} as const satisfies Record<PricingMode, string>;

/**
 * The regime is FROZEN (#187 §10): stated at declaration time, beside the
 * control, rather than discovered when the field turns out to be read-only.
 */
export const REGIME_CANNOT_CHANGE =
  "How a kind of work is sold cannot be changed once it is declared. To change it, " +
  "retire this kind of work and declare a replacement under a new key — and a key " +
  "change is an integration change for your code.";

/**
 * The posture trap (#187 §9, #151 §18): for a workspace that meters without
 * billing, the regime is recorded and inert — and turns into a start-gate
 * refusal the day billing is enabled. Said before that day, which is the whole
 * point of saying it.
 */
export const REGIME_IS_INERT_UNTIL_BILLING =
  "This workspace meters without billing, so the regime is recorded and changes nothing " +
  "today. The day billing is enabled, a fixed-price kind of work with no price in the " +
  "pricing book refuses to start.";

/** What to say beside the regime control, in the order it should be read. */
export function declarationNotes(opts: { meteringOnly: boolean }): readonly string[] {
  return opts.meteringOnly
    ? [REGIME_IS_INERT_UNTIL_BILLING, REGIME_CANNOT_CHANGE]
    : [REGIME_CANNOT_CHANGE];
}

/**
 * The COGS ceiling a run of this kind starts under: a number, from the
 * declaration or from the workspace default, or none at all.
 *
 * A union rather than a nullable number, so that the two sources that always
 * carry an amount cannot be asked to render one they do not have — the `?? 0`
 * a nullable field invites is the defect `apps/ui/CLAUDE.md` names.
 */
export type Ceiling =
  | { readonly source: "declaration" | "workspace"; readonly micros: number }
  | { readonly source: "uncapped" };

/**
 * The ceiling a run of this kind actually starts under.
 *
 * The declaration's own number when it names one; otherwise the workspace
 * default; otherwise none — and "none" is rendered as UNCAPPED rather than
 * left blank, because #150 §8 rules that uncapped is legal but never silent.
 * `null` while the workspace config has not arrived: a ceiling the console
 * does not yet know is not the same fact as no ceiling at all.
 */
export function effectiveCeiling(
  kind: Pick<KindOfWork, "default_provider_cost_limit_micros">,
  config: TenantConfig | undefined,
): Ceiling | null {
  if (kind.default_provider_cost_limit_micros != null) {
    return { source: "declaration", micros: kind.default_provider_cost_limit_micros };
  }
  if (config === undefined) return null;
  const workspace = config.default_task_provider_cost_limit_micros;
  if (workspace != null) return { source: "workspace", micros: workspace };
  return { source: "uncapped" };
}

/**
 * The ceiling, said so that "none" and "not yet known" cannot be confused
 * with a number or with each other.
 */
export function describeCeiling(ceiling: Ceiling | null, currency: string): string {
  if (ceiling === null) return ABSENT_LABEL;
  switch (ceiling.source) {
    case "declaration":
      return formatMicros(ceiling.micros, currency);
    case "workspace":
      return `${formatMicros(ceiling.micros, currency)} (workspace default)`;
    case "uncapped":
      return "Uncapped";
  }
}

/**
 * A duration in seconds as a person reads one, or `null` when there is none.
 *
 * The caller says what "none" means, because it differs by field: an absent
 * silence window is the workspace's own default, an absent deadline is no
 * deadline at all. A helper that chose one word would be wrong for the other.
 */
export function describeDuration(seconds: number | null | undefined): string | null {
  if (seconds == null) return null;
  if (seconds % 3_600 === 0) return `${seconds / 3_600} h`;
  if (seconds % 60 === 0) return `${seconds / 60} min`;
  return `${seconds} s`;
}

/** Live kinds first, then retired; each half by key. */
export function sortedKinds(kinds: readonly KindOfWork[]): KindOfWork[] {
  return [...kinds].sort(
    (a, b) =>
      Number(a.retired) - Number(b.retired) ||
      a.key.localeCompare(b.key) ||
      a.kind.localeCompare(b.kind),
  );
}

/** What a kind of work's runs were quoted: one figure, or the range of them. */
export interface PricedRuns {
  lowMicros: number;
  highMicros: number;
  /** How many of the runs read had pinned a price at all. */
  runCount: number;
}

/**
 * The price(s) a kind of work sold for, read off its runs.
 *
 * ⚠ THIS IS THE ONLY WIRE-BORNE PRICE A KIND OF WORK HAS. The amount is a
 * line in a pricing book, resolved for each customer from THEIR book at start
 * and pinned onto the run (`agreed_price_micros`); the registry deliberately
 * carries no number (#415, #187 §25 Q1). So "the price" of a kind is what its
 * runs were actually quoted — one figure when every book agrees, a range when
 * a customer's own book prices it differently — and a kind nobody has run yet
 * has no price to show a ceiling against, which is said rather than guessed.
 *
 * It follows that this LAGS a repricing by one run: a price changed in the
 * book shows here once a run has been quoted at it. The rendering says so.
 */
export function pricedRuns(
  runs: readonly Pick<RunRow, "agreed_price_micros">[],
): PricedRuns | null {
  const prices = runs
    .map((run) => run.agreed_price_micros)
    .filter((micros): micros is number => micros != null);
  if (prices.length === 0) return null;
  return {
    lowMicros: Math.min(...prices),
    highMicros: Math.max(...prices),
    runCount: prices.length,
  };
}

/**
 * The ceiling as a share of the price — #150 §5.4's own arithmetic: a $3.00
 * ceiling under a $5.00 price is 60%, and under a later $8.00 price is 37%,
 * with no signal. Rendering this beside the price is that signal.
 */
export function ceilingShare(ceilingMicros: number, priceMicros: number): number {
  return ceilingMicros / priceMicros;
}

/**
 * The share as a whole percentage, FLOORED: "37%" for three eighths, as #150
 * §5.4 itself writes it. Rounding up would overstate the headroom a run has
 * under its ceiling, and the conservative direction is the honest one here.
 *
 * `null` when the price is nothing. Zero is a price a tenant may agree to,
 * so a run quoted at no charge is real evidence — but a ceiling is not a
 * share of nothing, and saying so beats printing an infinity.
 */
export function describeShare(ceilingMicros: number, priceMicros: number): string | null {
  if (priceMicros <= 0) return null;
  return formatPercent(Math.floor(ceilingShare(ceilingMicros, priceMicros) * 100), 0);
}

/**
 * Whether a declaration with this identity already stands.
 *
 * The guard that keeps a blank form from replacing a standing kind of work:
 * the route is an idempotent PUT, so a new declaration under a standing
 * `(kind, key)` with the same regime is ACCEPTED — and its empty ceiling,
 * windows and grouping fields would silently become the kind's. Revising is a
 * different act, taken from the kind's own page.
 */
export function alreadyDeclared(
  standing: readonly KindOfWork[],
  target: Pick<KindOfWork, "kind" | "key">,
): boolean {
  return standing.some((kind) => sameDeclaration(kind, target));
}

/**
 * A standing kind of work, said back to the registry exactly as it stands.
 *
 * Built field by field rather than spread, because `retired_at` is the
 * registry's to stamp and not a caller's to send, and because a spread would
 * quietly carry whatever a future response adds.
 */
export function redeclare(kind: KindOfWork): KindOfWorkDeclaration {
  return {
    key: kind.key,
    kind: kind.kind,
    pricing_mode: kind.pricing_mode,
    default_provider_cost_limit_micros: kind.default_provider_cost_limit_micros ?? null,
    silence_window_seconds: kind.silence_window_seconds ?? null,
    absolute_deadline_seconds: kind.absolute_deadline_seconds ?? null,
    required_dimensions: [...kind.required_dimensions],
    retired: kind.retired,
  };
}

/**
 * The whole vocabulary, with one declaration added or revised.
 *
 * ⚠ THE ROUTE IS AN IDEMPOTENT PUT OVER THE COLLECTION, so a body that named
 * only the kind being changed would leave every other kind's ceiling and
 * windows replaced by nothing. Every standing declaration goes back verbatim.
 *
 * The one being revised is what the caller sent, with exactly the wire's own
 * reading of an omission: a policy field left out IS replaced (by nothing —
 * that is what the route does, and a helper that quietly kept the old value
 * would make "clear the window" impossible to say), while an omitted regime
 * and an omitted retirement keep what the row holds (the route leaves both
 * alone, and a standing regime re-sent is not a change; a different one is
 * refused by the server and never invented here).
 */
export function declarationBody(
  standing: readonly KindOfWork[],
  next: KindOfWorkDeclaration,
): DeclareKindsBody {
  const target = { kind: next.kind ?? "task", key: next.key };
  const matched = standing.find((kind) => sameDeclaration(kind, target));
  // Spelled out with the wire's own reading of every omission, so the body
  // says explicitly what the route would have assumed.
  const revised: KindOfWorkDeclaration = {
    key: next.key,
    kind: target.kind,
    pricing_mode: next.pricing_mode ?? matched?.pricing_mode ?? null,
    default_provider_cost_limit_micros: next.default_provider_cost_limit_micros ?? null,
    silence_window_seconds: next.silence_window_seconds ?? null,
    absolute_deadline_seconds: next.absolute_deadline_seconds ?? null,
    required_dimensions: [...(next.required_dimensions ?? [])],
    retired: next.retired ?? matched?.retired ?? null,
  };
  const task_types = standing.map((kind) =>
    sameDeclaration(kind, target) ? revised : redeclare(kind),
  );
  return { task_types: matched ? task_types : [...task_types, revised] };
}

/**
 * Every declaration under one routed key — usually one, but one word may name
 * a kind of work at either altitude and the two are different declarations.
 * The whole-work altitude comes first because it is the one a reader of
 * `/tasks/kinds/{key}` almost always means.
 */
export function declarationsUnderKey(
  kinds: readonly KindOfWork[],
  key: string,
): KindOfWork[] {
  const under = kinds.filter((kind) => kind.key === key);
  return [
    ...under.filter((kind) => kind.kind === "task"),
    ...under.filter((kind) => kind.kind !== "task"),
  ];
}
