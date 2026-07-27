import * as React from "react";

import { isNotFound } from "@/api/problem";
import { CopyButton } from "@/components/shared/copy-button";
import { DisabledHint } from "@/components/shared/disabled-hint";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorCard } from "@/components/shared/error-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useHasRole } from "@/hooks/use-current-role";
import { cardTypeLabel } from "@/lib/labels";
import { useBook } from "../api/queries";
import { AddRateDialog } from "./add-rate-dialog";
import { PublishDialog } from "./publish-dialog";
import { RatesTable } from "./rates-table";

/**
 * /pricing/$bookId — one rate-card book: identity header, its rates (active /
 * history / point-in-time), add rate, retire rate, and the publish (atomic
 * reprice) flow. Cross-page navigation arrives via injected callbacks so the
 * page renders without router context in tests.
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
  const isAdmin = useHasRole("admin");
  const [addOpen, setAddOpen] = React.useState(false);
  const [publishOpen, setPublishOpen] = React.useState(false);

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
          description="This rate-card book doesn't exist (or was created in another workspace)."
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
            <Badge variant="outline">{cardTypeLabel(data.card_type)}</Badge>
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
            <Badge variant="outline">v{data.version}</Badge>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <DisabledHint disabled={!isAdmin} hint="Requires the Admin role.">
            <Button
              variant="outline"
              size="sm"
              onClick={() => setAddOpen(true)}
              disabled={!isAdmin}
            >
              Add rate
            </Button>
          </DisabledHint>
          <DisabledHint disabled={!isAdmin} hint="Requires the Admin role.">
            <Button size="sm" onClick={() => setPublishOpen(true)} disabled={!isAdmin}>
              Publish new prices
            </Button>
          </DisabledHint>
        </div>
      </div>
      <p className="text-[12px] text-text-muted">
        {data.card_type === "price"
          ? "A price card: these rates set what customers are billed."
          : "A cost card: these rates derive what providers charge you (your COGS)."}{" "}
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

      <RatesTable book={data} isAdmin={isAdmin} onAddRate={() => setAddOpen(true)} />

      <AddRateDialog book={data} open={addOpen} onOpenChange={setAddOpen} />
      <PublishDialog book={data} open={publishOpen} onOpenChange={setPublishOpen} />
    </div>
  );
}
