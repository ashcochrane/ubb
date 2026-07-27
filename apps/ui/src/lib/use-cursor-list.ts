import { useCallback, useMemo, useState } from "react";
import {
  keepPreviousData,
  useQuery,
  type QueryKey,
} from "@tanstack/react-query";

/** The uniform cursor-paginated envelope every list endpoint returns. */
export interface CursorPage<T> {
  data: T[];
  next_cursor?: string | null;
  has_more: boolean;
}

export interface CursorPager<T> {
  /** Items on the current page (empty array while first load is pending). */
  items: T[];
  isLoading: boolean;
  isFetching: boolean;
  isError: boolean;
  error: unknown;
  /** 1-based index of the page currently shown. */
  page: number;
  hasPrev: boolean;
  hasNext: boolean;
  next: () => void;
  prev: () => void;
  /** Reset back to the first page — call when filters change. */
  reset: () => void;
  refetch: () => void;
}

/**
 * Drive a cursor-paginated endpoint with forward/back navigation.
 *
 * Maintains a stack of cursors so the user can page backwards even though the
 * API is forward-only. `queryKeyBase` should include any active filters so the
 * cache and reset behaviour stay correct.
 *
 *   const pager = useCursorList({
 *     queryKeyBase: ["customers", "list"],
 *     fetchPage: (cursor) => api.listCustomers({ cursor, limit }),
 *   });
 */
export function useCursorList<T>(opts: {
  queryKeyBase: QueryKey;
  fetchPage: (cursor: string | undefined) => Promise<CursorPage<T>>;
  enabled?: boolean;
  limit?: number;
}): CursorPager<T> {
  const { queryKeyBase, fetchPage, enabled = true } = opts;
  // Stack of cursors, one per visited page. `undefined` = the first page.
  const [cursors, setCursors] = useState<(string | undefined)[]>([undefined]);
  const cursor = cursors[cursors.length - 1];

  const query = useQuery({
    queryKey: [...queryKeyBase, "cursor", cursor ?? "__first__"],
    queryFn: () => fetchPage(cursor),
    enabled,
    placeholderData: keepPreviousData,
  });

  const next = useCallback(() => {
    const nextCursor = query.data?.next_cursor;
    if (!nextCursor) return;
    setCursors((prev) => [...prev, nextCursor]);
  }, [query.data?.next_cursor]);

  const prev = useCallback(() => {
    setCursors((prev) => (prev.length > 1 ? prev.slice(0, -1) : prev));
  }, []);

  const reset = useCallback(() => setCursors([undefined]), []);

  return useMemo(
    () => ({
      items: query.data?.data ?? [],
      isLoading: query.isLoading,
      isFetching: query.isFetching,
      isError: query.isError,
      error: query.error,
      page: cursors.length,
      hasPrev: cursors.length > 1,
      hasNext: Boolean(query.data?.has_more),
      next,
      prev,
      reset,
      refetch: () => void query.refetch(),
    }),
    [query, cursors.length, next, prev, reset],
  );
}
