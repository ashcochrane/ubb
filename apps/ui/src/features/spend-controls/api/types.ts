// Every spend-control read is fully typed in the generated schema — the two
// reports ship as typed rows on purpose (#465, slice 6 §14): the per-customer
// report they replaced was `additionalProperties: true`, which is how a console
// reader once coalesced an absent cost to zero money on the one report that
// itemises what overran a stop, and an untyped response is invisible to every
// enumeration derived from the contract. So this file holds aliases and one
// filter shape, and no narrowing.
//
// The reads sit at the root prefix and gate on no product (ADR-0011 §1's
// reasoning, restated in the route's own module): a unit of work's stops mean
// something for every tenant, and a family a workspace lacks answers no rows.

import type { RootSchemas } from "@/api/types";
import type { ControlFamily } from "@/lib/vocabulary";

export type StopsAndBreaches = RootSchemas["StopsAndBreachesResponse"];
export type CeilingEpisodeRow = RootSchemas["CeilingEpisodeRow"];
export type CustomerSpendPoolEpisodeRow = RootSchemas["CustomerSpendPoolEpisodeRow"];
export type WalletPolicyEpisodeRow = RootSchemas["WalletPolicyEpisodeRow"];
/** One row of the report — one of the three shapes, told apart in `../lib/episodes`. */
export type EpisodeRow = StopsAndBreaches["rows"][number];
export type ItemisedEvents = RootSchemas["ItemisedEventsOut"];
export type ItemisedEventRow = RootSchemas["ItemisedEventRow"];
export type FamilyTotalsRow = RootSchemas["SpendControlFamilyTotalsRow"];

export type UtilisationAndHeadroom = RootSchemas["UtilisationAndHeadroomResponse"];
/** One completed unit's ceiling as it stood at completion (#467; slice 6 §14). */
export type CeilingUtilisationRow = RootSchemas["CeilingUtilisationRow"];
/** The pool's status pair for the customer the filter names — the billing feature's own shape, re-published here. */
export type CustomerSpendPoolStatus = RootSchemas["CustomerSpendPoolStatusOut"];

/**
 * One choice in a customer picker.
 *
 * ⚠ **IT WAS A MARGIN ROW AND IS AN IDENTITY (#501).** This feature read the
 * per-customer margin list for the ids alone — every money field on it was
 * ignored here — and that route is gone with the other eight the one economic
 * query replaced. Grouping that query by the customer axis answers the same
 * question and nothing more, which is the shape this always wanted.
 */
export interface CustomerChoice {
  customer_id: string;
}

/**
 * The filters `GET /spend-controls/stops-and-breaches` takes, as the console
 * sends them. Every one is optional and every one is the route's own: a
 * customer (its work and its billing owner's customer-wide episodes), one
 * family, and a half-open datetime window on the instant each episode opened.
 * The kind-of-work filter the route also takes has no reader here yet — a
 * filter the mock would have to ignore is worse than one it does not offer
 * (#424's rule on the customer filter it left out).
 */
export interface StopsAndBreachesFilters {
  customer_id?: string;
  control_family?: ControlFamily;
  since?: string;
  until?: string;
}

/**
 * The filters `GET /spend-controls/utilisation-and-headroom` takes, as the
 * console sends them: the same customer and the same half-open window, on
 * the instant each unit completed. No family — the report is the Ceiling's
 * alone, with the pool's status pair beside it for a named customer — and
 * no kind-of-work filter, for the reason above.
 */
export interface UtilisationAndHeadroomFilters {
  customer_id?: string;
  since?: string;
  until?: string;
}
