// An episode row as this feature reasons about one: which of the three shapes
// it is, what each of its money pairs may be SAID to be, and the console's
// own sentences beside the facts the wire leaves null (#466; slice 6 §14,
// §18).
//
// NO NUMBER NOBODY KNOWS RENDERS AS A ZERO AMOUNT (#155 §9.2). Every amount
// on these rows arrives as a figure beside a COUNT of what it could not
// include — the itemised block's two pairs, a ceiling's crossed and final
// pairs, a pool's spend after the crossing — and `@/lib/total-reading` is the
// one place that decides whether such a figure is a figure, a floor, or
// nothing at all. Where the wire says null (a kill whose announcement aged
// out, a pool row that is gone, a balance no suspension announced), the
// reading is null too and a sentence below says so; nothing here coalesces.

import { labelMap } from "@/lib/localisation";
import { readTotal, type TotalReading } from "@/lib/total-reading";
import { CEILING_BASIS_LABEL_KEYS } from "@/lib/vocabulary";

import type {
  CeilingEpisodeRow,
  CustomerSpendPoolEpisodeRow,
  EpisodeRow,
  ItemisedEvents,
  WalletPolicyEpisodeRow,
} from "../api/types";

/** The catalogue's word for what a ceiling bounds — `cost` or `time`. */
export const ceilingBasisLabel = labelMap(CEILING_BASIS_LABEL_KEYS);

export type EpisodeShape =
  | { readonly shape: "ceiling"; readonly row: CeilingEpisodeRow }
  | { readonly shape: "customer_spend_pool"; readonly row: CustomerSpendPoolEpisodeRow }
  | { readonly shape: "wallet_policy"; readonly row: WalletPolicyEpisodeRow };

/**
 * Which of the three row shapes this is.
 *
 * Told by the required key each shape carries and the others lack — `task_id`
 * on a Ceiling row, `period` on a Customer spend pool row, `soft_floor` on a
 * Wallet policy row — which is the same disambiguation the SDK's generated
 * parser makes. `control_family` is the wire's discriminant and is what the
 * card RENDERS; it is not what narrows the type here, because every row schema
 * publishes the whole four-value enum on that field.
 */
export function episodeShape(row: EpisodeRow): EpisodeShape {
  if ("task_id" in row) return { shape: "ceiling", row };
  if ("period" in row) return { shape: "customer_spend_pool", row };
  return { shape: "wallet_policy", row };
}

// ---------------------------------------------------------------------------
// The readings

/** The billed pair an itemised block and a family's totals row both carry. */
export type BilledPair = Pick<ItemisedEvents, "billed_cost_micros" | "unpriced_event_count">;

/** The supplier-cost pair an itemised block and a family's totals row both carry. */
export type SupplierCostPair = Pick<
  ItemisedEvents,
  "provider_cost_micros" | "unresolved_event_count"
>;

/** The billed total over itemised events, beside how many prices it could not resolve. */
export function readItemisedPrice(pair: BilledPair): TotalReading {
  return readTotal(pair.billed_cost_micros, pair.unpriced_event_count);
}

/** The supplier-cost total over itemised events, beside how many costs it could not learn. */
export function readItemisedCost(pair: SupplierCostPair): TotalReading {
  return readTotal(pair.provider_cost_micros, pair.unresolved_event_count);
}

/**
 * The pair the ceiling FIRED on, as the kill announced it — or `null` where
 * the announcement no longer survives. Null is unknown, never zero: the wire
 * says nothing, and a reading of nothing is no reading.
 */
export function readCrossedCost(row: CeilingEpisodeRow): TotalReading | null {
  if (row.crossed_provider_cost_micros == null || row.crossed_unresolved_event_count == null) {
    return null;
  }
  return readTotal(row.crossed_provider_cost_micros, row.crossed_unresolved_event_count);
}

/** The pair the unit ENDED on, off its row: late events keep counting. */
export function readFinalCost(row: CeilingEpisodeRow): TotalReading {
  return readTotal(row.final_provider_cost_micros, row.final_unresolved_event_count);
}

/** The customer's charges that landed after a pool's crossing, as a pair. */
export function readSpentAfter(row: CustomerSpendPoolEpisodeRow): TotalReading {
  return readTotal(row.spent_after_micros, row.unpriced_after_count);
}

// ---------------------------------------------------------------------------
// The console's sentences beside the facts — copy, not catalogue content
// (ADR-0008 §4.5).

export const A_KILL_NEVER_RESUMES = "A kill never resumes, so this episode has no close.";

export const ANNOUNCEMENT_GONE =
  "The kill's announcement no longer survives, so the cost when the ceiling fired is unknown — not zero.";

export const CROSSING_MARKED =
  "The recording route marked this as the tipping event as it landed.";

export const CROSSING_REPLAYED =
  "Found by replaying the period's charges up to the instant the episode opened, against the pool's stop line as it stands now. A pool moved since can shift which posting this names.";

export const CROSSING_UNKNOWN =
  "Nothing UBB holds can name the charge that crossed this pool — not a guess.";

export const POOL_ROW_GONE = "The pool row is gone, so its amount is unknown.";

export const BALANCE_UNANNOUNCED =
  "No suspension announced a balance beside this stop, so the balance at crossing is unknown.";

export const FLOOR_GONE =
  "The control row no longer carries this floor, so the floor it crossed is unknown.";

export const SOFT_FLOOR_MARKER =
  "The soft floor winds new starts down and stops nothing, so this is a marker: there are no events to itemise.";

export const STILL_OPEN = "still open";

/** How the Charge that crossed a pool was found — or that it could not be. */
export function describeCrossing(row: CustomerSpendPoolEpisodeRow): string {
  if (row.crossing_charge_id == null) return CROSSING_UNKNOWN;
  return row.crossing_marked ? CROSSING_MARKED : CROSSING_REPLAYED;
}

/** Whether a unit is contained work, off the one fact that says so. */
export function containedWork(row: CeilingEpisodeRow): boolean {
  return row.parent_task_id != null;
}

/**
 * The identity a row renders under. A ceiling row is its unit's; a
 * customer-wide row is its customer's line and episode — the pair the
 * ledger numbers independently per line, so the line word is part of it.
 */
export function episodeKey(row: EpisodeRow): string {
  const episode = episodeShape(row);
  if (episode.shape === "ceiling") return episode.row.task_id;
  const line = episode.shape === "wallet_policy" && episode.row.soft_floor
    ? "soft_floor"
    : (episode.row.reason_code ?? episode.row.control_family);
  return `${episode.row.customer_id}:${line}:${episode.row.episode_seq}`;
}

/** "3 events" / "1 event". */
export function eventCount(count: number): string {
  return `${count.toLocaleString()} ${count === 1 ? "event" : "events"}`;
}
