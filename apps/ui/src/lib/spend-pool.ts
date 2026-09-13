// The Customer Spend Pool as the console reads and words it (#468; slice 6
// §4, §18; #150 §7).
//
// A POOL BOUNDS ONE CUSTOMER'S PERIOD CHARGES, and it is declared at one of
// two levels: on a customer — a seat or a business — or, for seats only, as
// the workspace default. A unit of work's charges count toward its seat's
// pool and toward its billing owner's pool where each exists (§4), so the
// customer's Billing tab says in words which of the two a reader is looking
// at, and the Billing page says the default is the seats' alone.
//
// THE PAIR IS READ, NEVER RECOMPUTED. The kernel composes the assessment
// (`core.crossing.spend_pool_assessment`) over the durable pair — the known
// period charges beside the count of postings whose revenue it could not
// include — and publishes it; the console renders what arrived. The known
// figure is a floor wherever that count is not zero, and the share and
// headroom beside it are then a floor and a most; unknown revenue is
// EXCLUDED and said to be, never summed as zero (#150 §4.2; #155 §9.2).
//
// THE POOL AND THE WALLET ANSWER DIFFERENT QUESTIONS (#151 §11.3), and the
// pool is blind to a price agreed at start until the work is delivered
// while the wallet's reservation sees it at start (#150 §7.5) — both are
// said in words beside the pair, because a reader who sees a pool at its
// line beside a balance that could pay for a hundred more starts has been
// shown two true things about two different bounds.
//
// IT SITS IN `lib/` BECAUSE TWO FEATURES RENDER THE WORDS: the customer's
// Billing tab (`features/customers`) and Utilisation and headroom
// (`features/spend-controls`, where the pair's readers were written in
// #467), with the Billing page (`features/billing`) binding the mode's word
// on the default. The console's imports only flow down, so the binding
// moved here the day the second feature rendered it — the rule
// `@/lib/pricing-mode` states (#425) and `@/lib/ceiling` followed (#467).
// Identity is the registry's (`@/lib/vocabulary`), expression the
// catalogue's (`@/locales`, through `@/lib/localisation`), and the
// sentences beside them are the console's own (ADR-0008 §4.5). The mode's
// hand-written map in the legacy adapter is deleted with this module; the
// set is CLOSED, so there is no unknown branch to render.

import type { RootSchemas } from "@/api/types";
import { labelMap } from "@/lib/localisation";
import { amountAtMost, shareAtLeast } from "@/lib/supplier-cost";
import { readTotal, type TotalReading } from "@/lib/total-reading";
import {
  SPEND_POOL_ENFORCE_MODE_LABEL_KEYS,
  SPEND_POOL_ENFORCE_MODE_VALUES,
  type SpendPoolEnforceMode,
} from "@/lib/vocabulary";

/** The pool's status pair as the wire carries it, every field required. */
export type CustomerSpendPoolStatus = RootSchemas["CustomerSpendPoolStatusOut"];

/** The title the pair renders under, wherever it renders. */
export const POOL_PAIR_TITLE = "Customer spend pool";

// ---------------------------------------------------------------------------
// The mode's words

/** The catalogue's words for how a pool is enforced. The set is closed. */
export const spendPoolEnforceModeLabel = labelMap(SPEND_POOL_ENFORCE_MODE_LABEL_KEYS);

/**
 * Every mode the registry declares with its catalogue word, in the
 * registry's order — what a form offers, and what a closed select shows for
 * its value. Built from the generated set so a mode the registry adds is
 * offered the day it is generated, and typed total over it so a reader can
 * index without a guard.
 */
export const SPEND_POOL_ENFORCE_MODE_WORDS = Object.fromEntries(
  SPEND_POOL_ENFORCE_MODE_VALUES.map((mode) => [mode, spendPoolEnforceModeLabel(mode)]),
) as Record<SpendPoolEnforceMode, string>;

/**
 * What the pool's posture means for a start — console-owned copy beside the
 * pair, total over the generated type so a mode the registry adds and this
 * has no sentence for fails `tsc`. Said in words as well as by the mode's
 * own word because the reader's question is not only "which mode" but "why
 * was nothing refused": an alert-only pool past its line refuses nothing,
 * and a blocking pool short of its line has not yet.
 */
export const POOL_POSTURE = {
  alert_only:
    "This pool alerts and never stops: however far the charges go past it, no start is refused by it.",
  blocking:
    "This pool stops: at or over its stop line, new starts are refused and active work is stopped.",
} as const satisfies Record<SpendPoolEnforceMode, string>;

// ---------------------------------------------------------------------------
// The status pair

/** The customer's known period charges, beside how many postings the figure could not price. */
export function readPoolCharges(pool: CustomerSpendPoolStatus): TotalReading {
  return readTotal(pool.known_period_charges_micros, pool.unresolved_posting_count);
}

/** Whether the pool's pair is a floor: the known charges left a posting unpriced. */
function poolPairIsFloor(pool: CustomerSpendPoolStatus): boolean {
  return pool.unresolved_posting_count > 0;
}

/** The share of the pool the known charges have used — a floor wherever the pair is. */
export function describePoolUtilisation(pool: CustomerSpendPoolStatus): string | null {
  if (pool.used_percentage === null) return null;
  return shareAtLeast(pool.used_percentage, poolPairIsFloor(pool));
}

/**
 * The headroom left under the pool — a most wherever the pair is a floor.
 * A zero past the line is SETTLED: the kernel clamps the headroom at
 * nothing, and a posting it could not price can only lower a figure that
 * is already at its floor, so it renders as the zero it is, not as a most.
 */
export function describePoolHeadroom(pool: CustomerSpendPoolStatus, currency: string): string | null {
  if (pool.remaining_micros === null) return null;
  const most = poolPairIsFloor(pool) && pool.remaining_micros > 0;
  return amountAtMost(pool.remaining_micros, currency, most);
}

/**
 * What the known figure left out, said beside it — the count of postings
 * whose revenue is unresolved, reported as EXCLUDED rather than folded in
 * as nothing (#150 §4.2). Null where the figure left nothing out, so a
 * whole figure carries no sentence about an exclusion it did not make.
 */
export function excludedFromKnown(pool: CustomerSpendPoolStatus): string | null {
  const count = pool.unresolved_posting_count;
  if (count <= 0) return null;
  const subject =
    count === 1
      ? "1 posting whose revenue UBB has not resolved is"
      : `${count.toLocaleString()} postings whose revenue UBB has not resolved are`;
  return `${subject} excluded from the known figure, not counted as zero.`;
}

// ---------------------------------------------------------------------------
// The console's sentences beside the pair — copy, not catalogue content
// (ADR-0008 §4.5).

export const STARTS_REFUSED =
  "The known charges are at or over the pool's stop line, so new starts for this customer are being refused.";

export const POOL_AND_WALLET_DIFFER =
  "The pool answers a different question from the wallet's affordability. The pool asks how much of one period's charges a customer has used against the bound declared for them; affordability asks whether their balance, less what is reserved, can pay for the next start. A large balance beside a small pool is coherent.";

export const POOL_BLIND_TO_FIXED_PRICE =
  "The pool is blind to work sold at one agreed price until that work is delivered; the wallet's reservation sees the price at start. Both are right about what they measure.";

/**
 * The level a pool applies to this customer at, derived from what is
 * declared on them beside what the status read says applies: a pool
 * declared here is theirs; none declared here with one still applying is
 * the workspace default, which reaches seats only; and none either way is
 * no pool.
 */
export type PoolLevel = "declared_here" | "seat_default" | "none";

export function poolLevel(
  declared: { readonly cap_micros: number },
  applies: { readonly cap_micros: number },
): PoolLevel {
  if (declared.cap_micros > 0) return "declared_here";
  if (applies.cap_micros > 0) return "seat_default";
  return "none";
}

/** The level in words, total over the three so a level with no sentence fails `tsc`. */
export const POOL_LEVEL = {
  declared_here:
    "Declared on this customer. Their charges count toward it — and toward their billing owner's pool as well, where they are a seat of a business that has one.",
  seat_default:
    "No pool is declared on this customer, so the workspace default for seats applies, as the Billing page declares it. A pool declared here replaces it for this customer.",
  none:
    "No pool applies to this customer: none is declared here, and the workspace default reaches seats only — a business never takes it, and a seat takes it only where one is declared.",
} as const satisfies Record<PoolLevel, string>;

/** The Billing page's word on the default: whose it is, and whose it is not. */
export const SEAT_DEFAULT_LEVEL =
  "The pool for every seat that declares none of its own — an individual customer, or a seat of a business. It reaches seats only: a business with no pool of its own has none, so one number never becomes a line at two altitudes.";
