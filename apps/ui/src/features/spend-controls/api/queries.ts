// TanStack Query hooks for the spend-controls feature. ALL query keys live
// here. First key segment = backend namespace — `spend-controls` is the reads'
// own prefix — so a money movement elsewhere can invalidate every report at
// once (`features/billing/api/queries.ts`, `features/customers/api/queries.ts`
// both do: a credit can clear a floor stop, which closes an episode here).

import { useQuery } from "@tanstack/react-query";

import { spendControlsApi } from "./provider";
import type { StopsAndBreachesFilters, UtilisationAndHeadroomFilters } from "./types";

export const spendControlKeys = {
  all: ["spend-controls"] as const,
  stopsAndBreaches: (filters: StopsAndBreachesFilters) =>
    ["spend-controls", "stops-and-breaches", filters] as const,
  utilisationAndHeadroom: (filters: UtilisationAndHeadroomFilters) =>
    ["spend-controls", "utilisation-and-headroom", filters] as const,
};

export function useStopsAndBreaches(filters: StopsAndBreachesFilters) {
  return useQuery({
    queryKey: spendControlKeys.stopsAndBreaches(filters),
    queryFn: () => spendControlsApi.getStopsAndBreaches(filters),
    // Window and filter changes refresh in the background without blanking.
    placeholderData: (previous) => previous,
  });
}

export function useUtilisationAndHeadroom(filters: UtilisationAndHeadroomFilters) {
  return useQuery({
    queryKey: spendControlKeys.utilisationAndHeadroom(filters),
    queryFn: () => spendControlsApi.getUtilisationAndHeadroom(filters),
    placeholderData: (previous) => previous,
  });
}

/**
 * The customer filter's choices. The SAME key the events feature caches the
 * margin list under, because it is the same raw response (apps/ui/CLAUDE.md:
 * same key ⇒ same cached shape); a projection would add a tail.
 */
export function useSpendControlCustomers() {
  return useQuery({
    queryKey: ["margin", "customers"] as const,
    queryFn: () => spendControlsApi.listCustomers(),
  });
}
