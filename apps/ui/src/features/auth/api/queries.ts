import { queryOptions, useQuery } from "@tanstack/react-query";
import { getMe } from "./api";

export const meQueryOptions = queryOptions({
  queryKey: ["me"] as const,
  queryFn: getMe,
  staleTime: Infinity,
});

export const useMe = () => useQuery(meQueryOptions);
