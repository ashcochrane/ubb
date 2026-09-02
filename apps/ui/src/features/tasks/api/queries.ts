// TanStack Query hooks for the tasks feature. ALL query keys and mutation
// invalidation live here. First key segment = backend namespace — and a unit
// of work is a KERNEL concept mounted at the root prefix, so its namespace is
// its own rather than a product's.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useCursorList } from "@/api/pagination";

import { tasksApi } from "./provider";
import type { DeclareKindsBody, RunsFilters } from "./types";

export function useKindsOfWork() {
  return useQuery({
    queryKey: ["tasks", "kinds"] as const,
    queryFn: () => tasksApi.listKinds(),
  });
}

/**
 * Declare the whole vocabulary of kinds of work.
 *
 * The body is the entire registry every time (see `declareKinds` in `./api`),
 * so the mutation takes it ready-built rather than one kind: the one place a
 * body is assembled is `declarationBody` in `../lib/kinds`, and a hook that
 * accepted a single declaration would be the place a standing kind's ceiling
 * quietly went missing.
 */
export function useDeclareKinds() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: DeclareKindsBody) => tasksApi.declareKinds(body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["tasks"] });
    },
  });
}

/** Top-level runs, narrowed; newest first, cursor-paged. */
export function useRuns(filters: RunsFilters, options?: { enabled?: boolean }) {
  return useCursorList(
    ["tasks", "runs", filters],
    (cursor) => tasksApi.listRuns(filters, cursor),
    options,
  );
}
