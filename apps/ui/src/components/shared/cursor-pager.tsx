import { ChevronLeft, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import type { CursorPager } from "@/lib/use-cursor-list";

/**
 * Prev/Next controls for a `useCursorList` pager. Renders nothing when there is
 * only a single page of results.
 */
export function CursorPagerControls<T>({
  pager,
  className,
}: {
  pager: CursorPager<T>;
  className?: string;
}) {
  if (!pager.hasPrev && !pager.hasNext) return null;
  return (
    <div className={className ?? "flex items-center justify-end gap-2 pt-1"}>
      <span className="mr-1 text-xs text-muted-foreground">Page {pager.page}</span>
      <Button
        variant="outline"
        size="sm"
        onClick={pager.prev}
        disabled={!pager.hasPrev || pager.isFetching}
      >
        <ChevronLeft />
        Prev
      </Button>
      <Button
        variant="outline"
        size="sm"
        onClick={pager.next}
        disabled={!pager.hasNext || pager.isFetching}
      >
        Next
        <ChevronRight />
      </Button>
    </div>
  );
}
