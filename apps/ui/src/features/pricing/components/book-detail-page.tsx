import * as React from "react";

import { isNotFound } from "@/api/problem";
import { CopyButton } from "@/components/shared/copy-button";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorCard } from "@/components/shared/error-card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useBook } from "../api/queries";
import { isCostBook, type AnyBook } from "../api/types";
import { BookChangesPanel } from "./book-changes-panel";
import { DeclareChangeDialog } from "./declare-change-dialog";
import { RulesTable } from "./rules-table";

/**
 * Which record the governance ledger files this book's changes under.
 *
 * The two kinds are two records with two sets of audit actions —
 * `pricing_book.declared` / `.withdrawn` and `cost_book.declared` / `.withdrawn`
 * — and the ledger's `resource_type` says which one moved. One shared word here
 * would put a reader asking *"when did we withdraw this PRICING book"* back to
 * reading metadata, which is the thing the split of those four action names
 * exists to prevent.
 */
function auditResourceType(book: AnyBook): string {
  return isCostBook(book) ? "cost_book" : "pricing_book";
}

/**
 * /pricing/$bookId — one book: what it is, what is about to change in it, and
 * the rules it holds (active / history / point-in-time). Cross-page navigation
 * arrives via injected callbacks so the page renders without router context in
 * tests.
 *
 * ⚠ **THE CHANGES PANEL SITS ABOVE THE RULES, AND THE ORDER IS THE ARGUMENT.**
 * A book's rules are what it does today; its pending changes are what it will
 * do, and the whole reason a change is declared before it is published is that
 * somebody reads it first. Putting the drafts below the table would bury the
 * one thing on this page that is still a decision.
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
  /**
   * Opens the audit trail filtered to this book, injected by the route file.
   *
   * ⚠ **THE PAGE DECIDES WHICH RECORD THE FILTER NAMES, NOT THE ROUTE (#368).**
   * The ledger records a Pricing Book and a cost book under their own resource
   * types, because they are two records — so a route file that hard-coded one
   * word would send half the books on this screen to an empty trail. It is
   * derived from the book in hand and handed over, which also means the day a
   * third kind of book exists there is one place to change.
   */
  onShowAuditTrail?: (filter: {
    resource_type: string;
    resource_id: string;
  }) => void;
}) {
  const book = useBook(bookId);
  const [declareOpen, setDeclareOpen] = React.useState(false);

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
              <>
                {data.is_default && <Badge variant="secondary">Default</Badge>}
                {data.customer_id && (
                  <Badge variant="secondary">One customer’s own rules</Badge>
                )}
              </>
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
            onClick={() =>
              onShowAuditTrail({
                resource_type: auditResourceType(data),
                resource_id: data.id,
              })
            }
            className="underline underline-offset-2 hover:text-text-primary"
          >
            Who changed this book?
          </button>
        )}
      </p>

      <BookChangesPanel book={data} onDeclareChange={() => setDeclareOpen(true)} />

      <RulesTable book={data} />

      <DeclareChangeDialog
        book={data}
        open={declareOpen}
        onOpenChange={setDeclareOpen}
      />
    </div>
  );
}
