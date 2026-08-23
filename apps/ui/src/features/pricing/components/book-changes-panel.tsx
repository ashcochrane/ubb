import * as React from "react";
import { CalendarClock } from "lucide-react";

import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { DisabledHint } from "@/components/shared/disabled-hint";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorCard } from "@/components/shared/error-card";
import { LoadMore } from "@/components/shared/load-more";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useHasRole } from "@/hooks/use-current-role";
import { formatDate } from "@/lib/format";
import { toastOnError, toastSuccess } from "@/lib/mutations";
import {
  useBookPublishes,
  useDiscardBookPublish,
  usePublishBookPublish,
} from "../api/queries";
import type { AnyBook, BookPublish } from "../api/types";
import { PublishDiff } from "./publish-diff";

/**
 * What is about to happen to this book's prices.
 *
 * ⚠ **A SERIES, NOT A PENDING ITEM.** There is no limit on how many changes a
 * book may have scheduled at once, and a panel that showed "the next change"
 * would hide every one after it — which is exactly what a tenant dating
 * changes forward is trying to see. So every draft is a row, ordered by the
 * instant it takes effect, and the panel says how many are waiting.
 *
 * ⚠ **A REVERSAL IS A SECOND ROW, NOT A MISSING ONE.** The contract admits a
 * change landing exactly on a boundary already scheduled and says outright that
 * this is how a scheduled change is reversed. So undoing a scheduled rise adds
 * a row after it, both stay visible, and a tenant reads the pair as *"we put
 * it up and then we put it back"* — which is what happened. Removing the first
 * row would be the console deciding a declaration somebody made had never been
 * made.
 *
 * ⚠ **DISCARD IS OFFERED ON A DRAFT AND NEVER ON A PUBLISHED RECORD.** A draft
 * closed nothing, so discarding it reopens nothing and the book is left exactly
 * as it stood. A publish that has already closed and opened rules is not an
 * intention that can be withdrawn — the act that undoes one is a further
 * publish — and the API refuses it, so a button here would be a button pointed
 * at a refusal.
 */
export function BookChangesPanel({
  book,
  onDeclareChange,
}: {
  book: AnyBook;
  /** Opens the rule editor, injected so this panel owns no dialog state. */
  onDeclareChange?: () => void;
}) {
  const isAdmin = useHasRole("admin");
  const publishes = useBookPublishes(book.id);
  const currency = "currency" in book ? book.currency : "usd";

  const rows = publishes.rows;
  const scheduled = rows.filter((row) => isScheduled(row));

  return (
    // A named region rather than a bare div: the diff and the rules table below
    // render the same amounts for the same rules — the whole point of a diff —
    // so "is this figure on the screen" is a question that has to be asked of
    // one of them. A reader using a screen reader gets the same benefit.
    <section aria-label="Changes to this book" className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="min-w-0">
          <p className="text-[13px] font-medium text-text-primary">Changes</p>
          <p className="text-[12px] text-text-secondary">
            {rows.length === 0
              ? "Nothing is waiting to change in this book."
              : scheduled.length > 0
                ? `${rows.length} ${rows.length === 1 ? "change is" : "changes are"} waiting, ${scheduled.length} of them dated ahead.`
                : `${rows.length} ${rows.length === 1 ? "change is" : "changes are"} waiting.`}
          </p>
        </div>
        {onDeclareChange && (
          <DisabledHint disabled={!isAdmin} hint="Requires the Admin role.">
            <Button size="sm" onClick={onDeclareChange} disabled={!isAdmin}>
              Change this book
            </Button>
          </DisabledHint>
        )}
      </div>

      {publishes.isInitialLoading ? (
        <Card size="sm" className="p-3">
          <div className="space-y-2">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        </Card>
      ) : publishes.isError ? (
        <ErrorCard
          error={publishes.error}
          onRetry={() => void publishes.refetch()}
          title="Couldn't load this book's pending changes"
        />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={CalendarClock}
          title="No changes pending"
          description="A book changes by declaring what you want to happen, reading the diff, and publishing it. Nothing is written until you publish."
          action={
            isAdmin && onDeclareChange
              ? { label: "Change this book", onClick: onDeclareChange }
              : undefined
          }
        />
      ) : (
        <div className="space-y-2">
          {rows.map((publish) => (
            <PendingChangeRow
              key={publish.id}
              book={book}
              publish={publish}
              currency={currency}
              canAct={isAdmin}
            />
          ))}
          <LoadMore
            shownCount={rows.length}
            hasMore={publishes.hasMore}
            isFetchingNextPage={publishes.isFetchingNextPage}
            onLoadMore={publishes.fetchNextPage}
            noun="changes"
          />
        </div>
      )}
    </section>
  );
}

/** Whether a change takes effect later rather than the moment it is published. */
function isScheduled(publish: BookPublish): boolean {
  return new Date(publish.effective_at).getTime() > Date.now();
}

function PendingChangeRow({
  book,
  publish,
  currency,
  canAct,
}: {
  book: AnyBook;
  publish: BookPublish;
  currency: string;
  canAct: boolean;
}) {
  const publishIt = usePublishBookPublish(book.id);
  const discardIt = useDiscardBookPublish(book.id);
  const scheduled = isScheduled(publish);
  const busy = publishIt.isPending || discardIt.isPending;
  // ⚠ BOTH ACTS ARE CONFIRMED, AND NEITHER IS UNDONE BY REPEATING IT.
  // Publishing closes rules and opens their replacements; what undoes one is a
  // FURTHER publish, which is a decision rather than an undo button. Discarding
  // leaves the book untouched — that is the whole point of a draft — but the
  // declaration is gone, and rebuilding it means retyping every change in it.
  // The console's UX rule asks for a confirmation with consequence copy on
  // exactly this shape of act, and the consequences differ, so the two get two
  // sentences rather than one dialog with the verb swapped.
  const [confirming, setConfirming] = React.useState<"publish" | "discard" | null>(
    null,
  );
  const changeCount = publish.diff?.length ?? 0;

  return (
    <Card size="sm" className="gap-0 p-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={scheduled ? "secondary" : "outline"}>
              {scheduled ? "Scheduled" : "Takes effect now"}
            </Badge>
            <span className="text-[12px] text-text-secondary">
              {scheduled
                ? `This book changes on ${formatDate(publish.effective_at)}`
                : `Effective ${formatDate(publish.effective_at)}`}
            </span>
          </div>
          <p className="mt-0.5 text-[11px] text-text-muted">
            Declared by {publish.actor_display}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <DisabledHint disabled={!canAct} hint="Requires the Admin role.">
            <Button
              size="sm"
              variant="outline"
              disabled={!canAct || busy}
              onClick={() => setConfirming("discard")}
            >
              Discard
            </Button>
          </DisabledHint>
          <DisabledHint disabled={!canAct} hint="Requires the Admin role.">
            <Button
              size="sm"
              disabled={!canAct || busy}
              onClick={() => setConfirming("publish")}
            >
              Publish
            </Button>
          </DisabledHint>
        </div>
      </div>
      <div className="mt-2.5">
        <PublishDiff
          rows={publish.diff}
          currency={currency}
          unavailableReason={publish.diff_unavailable_reason}
        />
      </div>

      <ConfirmDialog
        open={confirming === "publish"}
        onOpenChange={(open) => {
          if (!open) setConfirming(null);
        }}
        title={scheduled ? "Publish this scheduled change?" : "Publish this change?"}
        description={
          scheduled
            ? `This writes ${changeCount === 1 ? "the rule" : `all ${changeCount} rules`} now, to take effect on ${formatDate(publish.effective_at)} — nothing runs on the day. Once published, the only way to undo it is to publish a further change.`
            : `This closes each superseded rule and opens its replacement, from ${changeCount === 1 ? "this change" : `all ${changeCount} changes`}, immediately. Once published, the only way to undo it is to publish a further change.`
        }
        confirmLabel="Publish"
        pending={publishIt.isPending}
        onConfirm={() =>
          publishIt.mutate(publish.id, {
            onSuccess: () => {
              setConfirming(null);
              toastSuccess(
                "Change published",
                scheduled
                  ? "The rules are written now and take effect at the instant you set."
                  : "The rules are written.",
              );
            },
            onError: toastOnError("Couldn't publish this change"),
          })
        }
      />

      <ConfirmDialog
        open={confirming === "discard"}
        onOpenChange={(open) => {
          if (!open) setConfirming(null);
        }}
        title="Discard this change?"
        description={`The book keeps exactly the rules it has now — a draft closed nothing, so this reopens nothing. What goes is the declaration itself: ${changeCount === 1 ? "this change" : `all ${changeCount} of these changes`} would have to be stated again.`}
        confirmLabel="Discard"
        destructive
        pending={discardIt.isPending}
        onConfirm={() =>
          discardIt.mutate(publish.id, {
            onSuccess: () => {
              setConfirming(null);
              toastSuccess(
                "Change discarded",
                "The book is exactly as it was — a draft closed nothing.",
              );
            },
            onError: toastOnError("Couldn't discard this change"),
          })
        }
      />
    </Card>
  );
}
