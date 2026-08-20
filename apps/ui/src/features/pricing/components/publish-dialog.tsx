import * as React from "react";

import { problemMessage } from "@/api/problem";
import { DisabledHint } from "@/components/shared/disabled-hint";
import { ErrorCard } from "@/components/shared/error-card";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import { toastSuccess } from "@/lib/mutations";
import { usePublishBook, useRates } from "../api/queries";
import type { Book, RateChangeIn } from "../api/types";
import { sameRateValues } from "../lib/pricing-math";
import { editToShape, initialEdit, type RowEdit } from "../lib/publish-edits";
import { PublishRow } from "./publish-row";

/**
 * Publish = atomic reprice. Edits are staged per active rate; unchanged rows
 * are excluded from the payload; the whole set applies all-or-nothing and
 * bumps the book version once.
 */
export function PublishDialog({
  book,
  open,
  onOpenChange,
}: {
  book: Book;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const activeRates = useRates(book.id, {}, { enabled: open });
  const publish = usePublishBook(book.id);
  const [edits, setEdits] = React.useState<Record<string, RowEdit>>({});

  React.useEffect(() => {
    if (open) {
      setEdits({});
      publish.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const rows = activeRates.rows.map((rate) => {
    const edit = edits[rate.id] ?? initialEdit(rate);
    const next = editToShape(edit);
    const changed = next !== null && !sameRateValues(next, rate);
    return { rate, edit, next, changed, invalid: next === null };
  });
  const changedRows = rows.filter((row) => row.changed);
  const hasInvalid = rows.some((row) => row.invalid);

  const onConfirm = () => {
    const changes: RateChangeIn[] = changedRows.map(({ rate, next }) => ({
      measurement_key: rate.measurement_key,
      provider: rate.provider,
      event_type: rate.event_type,
      task_type: rate.task_type,
      subtask_type: rate.subtask_type,
      grouping_field_1: rate.grouping_field_1,
      grouping_field_2: rate.grouping_field_2,
      grouping_field_3: rate.grouping_field_3,
      grouping_field_4: rate.grouping_field_4,
      grouping_field_5: rate.grouping_field_5,
      grouping_field_6: rate.grouping_field_6,
      grouping_field_7: rate.grouping_field_7,
      grouping_field_8: rate.grouping_field_8,
      grouping_field_9: rate.grouping_field_9,
      grouping_field_10: rate.grouping_field_10,
      rate_structure: next?.rate_structure ?? null,
      rate_per_unit_micros: next?.rate_per_unit_micros ?? null,
      unit_quantity: next?.unit_quantity ?? null,
      fixed_micros: next?.fixed_micros ?? null,
    }));
    publish.mutate(
      { changes },
      {
        onSuccess: (updated) => {
          toastSuccess(
            `Published v${updated.version}`,
            `${changes.length} ${changes.length === 1 ? "rate" : "rates"} repriced; previous versions kept in history.`,
          );
          onOpenChange(false);
        },
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Publish new prices</DialogTitle>
          <DialogDescription>
            Edit the values you want to change. Atomically supersedes the
            matched active rates and bumps the book to v{book.version + 1}.
            History is preserved; already-settled events are not touched.
          </DialogDescription>
        </DialogHeader>

        {activeRates.isInitialLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-14 w-full" />
            <Skeleton className="h-14 w-full" />
          </div>
        ) : activeRates.isError ? (
          <ErrorCard
            error={activeRates.error}
            onRetry={() => void activeRates.refetch()}
            title="Couldn't load the active rates"
          />
        ) : rows.length === 0 ? (
          <p className="rounded-lg border border-dashed border-border px-4 py-6 text-center text-sm text-text-secondary">
            This book has no active rates to reprice.
          </p>
        ) : (
          <div className="max-h-[50vh] space-y-2 overflow-y-auto pr-1">
            {rows.map(({ rate, edit, next, changed, invalid }) => (
              <PublishRow
                key={rate.id}
                rate={rate}
                edit={edit}
                next={next}
                changed={changed}
                invalid={invalid}
                currency={book.currency}
                onEdit={(nextEdit) =>
                  setEdits((current) => ({ ...current, [rate.id]: nextEdit }))
                }
              />
            ))}
          </div>
        )}

        {publish.isError && (
          <p className="text-xs text-destructive">
            {problemMessage(publish.error)} No prices were changed — the publish
            is all-or-nothing.
          </p>
        )}
        <DialogFooter className="items-center gap-3 sm:justify-between">
          <span className="text-[12px] text-text-secondary">
            {changedRows.length} of {rows.length}{" "}
            {rows.length === 1 ? "rate" : "rates"} will be repriced
            {hasInvalid ? " — fix the highlighted values first" : ""}.
          </span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={publish.isPending}
            >
              Cancel
            </Button>
            <DisabledHint
              disabled={changedRows.length === 0}
              hint="Change at least one value to publish."
            >
              <Button
                onClick={onConfirm}
                disabled={changedRows.length === 0 || hasInvalid || publish.isPending}
              >
                {publish.isPending ? "Working…" : `Publish v${book.version + 1}`}
              </Button>
            </DisabledHint>
          </div>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
