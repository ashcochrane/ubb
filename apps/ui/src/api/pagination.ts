// The one house pagination envelope (ADR "Paginated[T]"): every list endpoint
// answers { data, has_more, next_cursor } with `cursor` + `limit` query params
// (limit default 50, server-clamped 1..100, newest first, no total counts).
//
// UI consequence: lists are "Load more" / infinite lists — there is no page
// count and no "N of M". Drive paging off `has_more`; `next_cursor` may be
// absent OR null on the last page.

import {
  useInfiniteQuery,
  type QueryKey,
  type UseInfiniteQueryResult,
} from "@tanstack/react-query";

export interface CursorPage<T> {
  data: T[];
  has_more: boolean;
  next_cursor?: string | null;
}

export interface CursorListResult<T>
  extends Pick<
    UseInfiniteQueryResult<unknown, Error>,
    | "isLoading"
    | "isError"
    | "error"
    | "isFetching"
    | "isFetchingNextPage"
    | "refetch"
  > {
  /** All rows fetched so far, flattened in server order (newest first). */
  rows: T[];
  hasMore: boolean;
  fetchNextPage: () => void;
  /** True while the FIRST page is loading (skeleton state). */
  isInitialLoading: boolean;
}

/**
 * Cursor-list hook over the house envelope.
 *
 * const grants = useCursorList(
 *   ["billing", "grants", customerId, { status }],
 *   (cursor) => billingApiFns.listGrants(customerId, { status, cursor }),
 * );
 */
export function useCursorList<T>(
  queryKey: QueryKey,
  fetchPage: (cursor: string | undefined) => Promise<CursorPage<T>>,
  options?: { enabled?: boolean; limit?: number },
): CursorListResult<T> {
  const query = useInfiniteQuery({
    queryKey,
    queryFn: ({ pageParam }) => fetchPage(pageParam),
    initialPageParam: undefined as string | undefined,
    getNextPageParam: (lastPage) =>
      lastPage.has_more && lastPage.next_cursor ? lastPage.next_cursor : undefined,
    enabled: options?.enabled,
  });

  return {
    rows: query.data?.pages.flatMap((page) => page.data) ?? [],
    hasMore: query.hasNextPage,
    fetchNextPage: () => {
      if (!query.isFetchingNextPage) void query.fetchNextPage();
    },
    isInitialLoading: query.isLoading,
    isLoading: query.isLoading,
    isError: query.isError,
    error: query.error,
    isFetching: query.isFetching,
    isFetchingNextPage: query.isFetchingNextPage,
    refetch: query.refetch,
  };
}
