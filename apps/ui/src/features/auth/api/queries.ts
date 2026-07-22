import { queryOptions, useQuery } from "@tanstack/react-query";
import { authApi } from "./provider";

export const meQueryOptions = queryOptions({
  queryKey: ["me"] as const,
  queryFn: () => authApi.getMe(),
  staleTime: Infinity,
});

export const useMe = () => useQuery(meQueryOptions);
