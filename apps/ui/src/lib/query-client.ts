import { QueryClient } from "@tanstack/react-query";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
      gcTime: 5 * 60_000,
      refetchOnWindowFocus: true,
      // Pages own their error states (empty/error cards per section) rather
      // than throwing every fetch failure to the route boundary.
      throwOnError: false,
    },
    mutations: {
      retry: 0,
    },
  },
});
