// Real API calls for the spend-controls feature. Every call goes through
// `unwrap` so failures always reject with a typed ApiProblem.
//
// On `rootApi` (#465): the spend-control reports read across the kernel's
// ceiling, billing's pool and wallet policy, and belong to no product prefix.

import { meteringApi, rootApi } from "@/api/client";
import { unwrap } from "@/api/problem";
import {
  customerIdsIn,
  FIELD_AXIS,
  SUPPLIER_COGS,
} from "@/lib/economic-query";


import type {
  CustomerChoice,
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

/** Every customer the window's work reached — the filter's choices. */
export async function listCustomers(): Promise<CustomerChoice[]> {
  const answer = unwrap(
    await meteringApi.GET("/analytics/economics", {
      params: {
        query: { measures: [SUPPLIER_COGS], group_by: [FIELD_AXIS("customer")] },
      },
    }),
  );
  return customerIdsIn(answer).map((customer_id) => ({ customer_id }));
}
