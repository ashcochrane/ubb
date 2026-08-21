import { isNotFound } from "@/api/problem";
import { CopyButton } from "@/components/shared/copy-button";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorCard } from "@/components/shared/error-card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useBook } from "../api/queries";
import { isCostBook } from "../api/types";
import { RatesTable } from "./rates-table";

/**
 * /pricing/$bookId — one book: identity header and its rules (active /
 * history / point-in-time). Cross-page navigation arrives via injected
 * callbacks so the page renders without router context in tests.
 *
 * ⚠ **IT READS AND DOES NOT WRITE (#367, #368).** The three immediate
 * mutation surfaces this page used to offer — add a rule, retire one, reprice
 * a set of them — are deleted with the acts they recorded: every change to a
 * book is a declared publish now, read as a diff before it is committed to.
 * The feature that speaks that body arrives with #372, and until then the gap
 * is visible rather than hidden.
 *
 * The header shows what the book IS, and the two kinds show different things
 * because they ARE different things: a cost book names the supplier it records
 * and the currency that supplier bills in, a Pricing Book names neither.
 */
export function BookDetailPage({
  bookId,
  onBackToPricing,
  onShowAuditTrail,
}: {
  bookId: string;
  /** SPA navigation back to /pricing, injected by the route file. */
  onBackToPricing?: () => void;
  /** Opens the audit trail filtered to this book, injected by the route file. */
  onShowAuditTrail?: () => void;
}) {
  const book = useBook(bookId);

  if (book.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-7 w-64" />
        <Skeleton className="h-4 w-96" />
        <Skeleton className="h-40 w-full" />
      </div>
    );
  }
  if (book.isError) {
    if (isNotFound(book.error)) {
      return (
        <EmptyState
          title="Book not found"
          description="This book doesn't exist (or was created in another workspace)."
          action={{
            label: "Back to pricing",
            onClick: onBackToPricing ?? (() => undefined),
          }}
        />
      );
    }
    return (
      <ErrorCard
        error={book.error}
        onRetry={() => void book.refetch()}
        title="Couldn't load this book"
      />
    );
  }
  if (!book.data) return null;
  const data = book.data;

  return (
    <div className="space-y-4">
      <button
        type="button"
        onClick={onBackToPricing}
        className="text-[12px] text-text-secondary underline-offset-2 hover:underline"
      >
        ← All pricing
      </button>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="truncate text-xl font-semibold tracking-tight">
            {data.name || data.key}
          </h1>
          <div className="mt-1.5 flex flex-wrap items-center gap-2">
            <span className="font-mono text-[12px] text-text-secondary">{data.key}</span>
            <CopyButton value={data.key} label="Copy book key" />
            <Badge variant="outline">
              {isCostBook(data) ? "Cost book" : "Pricing book"}
            </Badge>
            {isCostBook(data) ? (
              <>
                {data.is_default && (
                  <Badge variant="secondary">
                    Default{data.provider_key ? ` for ${data.provider_key}` : ""}
                  </Badge>
                )}
                {!data.is_default && data.provider_key && (
                  <span className="text-[12px] text-text-secondary">
                    Provider: <span className="font-mono">{data.provider_key}</span>
                  </span>
                )}
                <span className="text-[12px] uppercase text-text-secondary">
                  {data.currency}
                </span>
              </>
            ) : (
              data.is_default && <Badge variant="secondary">Default</Badge>
            )}
            <Badge variant="outline">v{data.version}</Badge>
          </div>
        </div>
      </div>
      <p className="text-[12px] text-text-muted">
        {isCostBook(data)
          ? "A cost book: these rules derive what one supplier charges you (your COGS)."
          : "A pricing book: these rules set what your customers are billed."}{" "}
        {onShowAuditTrail && (
          <button
            type="button"
            onClick={onShowAuditTrail}
            className="underline underline-offset-2 hover:text-text-primary"
          >
            Who changed this book?
          </button>
        )}
      </p>

      <RatesTable book={data} />
    </div>
  );
}
