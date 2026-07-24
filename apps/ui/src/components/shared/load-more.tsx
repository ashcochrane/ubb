import { Button } from "@/components/ui/button";

/**
 * Footer control for cursor-paginated lists (the API has no total counts —
 * "Showing N" + Load more is the honest presentation).
 */
export function LoadMore({
  shownCount,
  hasMore,
  isFetchingNextPage,
  onLoadMore,
  noun = "rows",
}: {
  shownCount: number;
  hasMore: boolean;
  isFetchingNextPage: boolean;
  onLoadMore: () => void;
  noun?: string;
}) {
  return (
    <div className="flex items-center justify-between border-t border-border px-3 py-2">
      <span className="text-[11px] text-text-muted">
        Showing {shownCount.toLocaleString()} {noun}
        {hasMore ? " — more available" : ""}
      </span>
      {hasMore && (
        <Button
          variant="outline"
          size="sm"
          onClick={onLoadMore}
          disabled={isFetchingNextPage}
        >
          {isFetchingNextPage ? "Loading…" : "Load more"}
        </Button>
      )}
    </div>
  );
}
