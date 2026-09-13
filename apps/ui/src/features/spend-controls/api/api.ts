// Real API calls for the spend-controls feature. Every call goes through
// `unwrap` so failures always reject with a typed ApiProblem.
//
// On `rootApi` (#465): the spend-control reports read across the kernel's
// ceiling, billing's pool and wallet policy, and belong to no product prefix.

import { marginApi, rootApi } from "@/api/client";
import { unwrap } from "@/api/problem";

import type {
  MarginCustomers,
  StopsAndBreaches,
  StopsAndBreachesFilters,
  UtilisationAndHeadroom,
  UtilisationAndHeadroomFilters,
} from "./types";

/** What was spent past a stop, and why — typed rows per control that fired, in the window. */
export async function getStopsAndBreaches(
  filters: StopsAndBreachesFilters,
): Promise<StopsAndBreaches> {
  return unwrap(
    await rootApi.GET("/spend-controls/stops-and-breaches", {
      params: { query: { ...filters } },
    }),
  );
}

/** How much of each ceiling was used, and how often it could not be evaluated — per completed unit, then in aggregate. */
export async function getUtilisationAndHeadroom(
  filters: UtilisationAndHeadroomFilters,
): Promise<UtilisationAndHeadroom> {
  return unwrap(
    await rootApi.GET("/spend-controls/utilisation-and-headroom", {
      params: { query: { ...filters } },
    }),
  );
}

/** Every customer with a margin row — the customer filter's choices. */
export async function listCustomers(): Promise<MarginCustomers> {
  return unwrap(await marginApi.GET("/customers"));
}
