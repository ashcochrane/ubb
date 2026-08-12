import * as React from "react";
import { Layers } from "lucide-react";

import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { DisabledHint } from "@/components/shared/disabled-hint";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorCard } from "@/components/shared/error-card";
import { LoadMore } from "@/components/shared/load-more";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatDate, formatMicros, formatPrice, formatShortDate } from "@/lib/format";
import { pricingModelLabel } from "@/lib/labels";
import { cn } from "@/lib/utils";
import { toastOnError, toastSuccess } from "@/lib/mutations";
import { useRates, useRetireRate } from "../api/queries";
import type { Book, Rate } from "../api/types";

/**
 * A book's rates: active by default, optional full history, optional
 * point-in-time ("as of") view. Retiring soft-expires a rate (history kept).
 */
export function RatesTable({
  book,
  isAdmin,
  onAddRate,
}: {
  book: Book;
  isAdmin: boolean;
  onAddRate: () => void;
}) {
  const [includeHistory, setIncludeHistory] = React.useState(false);
  const [asOfLocal, setAsOfLocal] = React.useState("");
  const asOfIso = React.useMemo(() => {
    if (!asOfLocal) return undefined;
    const parsed = new Date(asOfLocal);
    return Number.isNaN(parsed.getTime()) ? undefined : parsed.toISOString();
  }, [asOfLocal]);

  const rates = useRates(book.id, { include_history: includeHistory, as_of: asOfIso });
  const [retireTarget, setRetireTarget] = React.useState<Rate | null>(null);
  const retire = useRetireRate(book.id);

  const pointInTime = asOfIso !== undefined;

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-x-5 gap-y-2">
        <div className="flex items-center gap-2">
          <Switch
            checked={includeHistory}
            onCheckedChange={setIncludeHistory}
            disabled={pointInTime}
            aria-label="Include history"
          />
          <Label className={cn(pointInTime && "opacity-50")}>Include history</Label>
        </div>
        <div className="flex items-center gap-2">
          <Label htmlFor="rates-as-of">As of</Label>
          <Input
            id="rates-as-of"
            type="datetime-local"
            className="h-8 w-[210px] text-[12px]"
            value={asOfLocal}
            onChange={(event) => setAsOfLocal(event.target.value)}
          />
          {pointInTime && (
            <Button variant="ghost" size="sm" onClick={() => setAsOfLocal("")}>
              Clear
            </Button>
          )}
        </div>
      </div>
      <p className="text-[11px] text-text-muted">
        {pointInTime
          ? `Showing the rates that were in force on ${formatDate(asOfIso ?? "")}. The point-in-time view overrides "Include history".`
          : includeHistory
            ? "Showing every version — superseded and retired rates carry an end date and appear muted."
            : "Showing active rates only. Toggle history to see superseded versions, or pick a moment to see the rates in force then."}
      </p>

      {rates.isInitialLoading ? (
        <Card size="sm" className="p-3">
          <div className="space-y-2">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
          </div>
        </Card>
      ) : rates.isError ? (
        <ErrorCard
          error={rates.error}
          onRetry={() => void rates.refetch()}
          title="Couldn't load this book's rates"
        />
      ) : rates.rows.length === 0 ? (
        pointInTime || includeHistory ? (
          <EmptyState
            icon={Layers}
            title="No rates for this view"
            description={
              pointInTime
                ? "No rates were in force at that moment. Clear the date to see the current rates."
                : "This book has no rate versions yet."
            }
          />
        ) : (
          <EmptyState
            icon={Layers}
            title="No rates yet"
            description="Add the first rate so events carrying this book's measurements get priced."
            action={isAdmin ? { label: "Add rate", onClick: onAddRate } : undefined}
          />
        )
      ) : (
        <Card size="sm" className="gap-0 py-0">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Measurement</TableHead>
                  <TableHead>Matchers</TableHead>
                  <TableHead>Model</TableHead>
                  <TableHead>Rate</TableHead>
                  <TableHead>Fixed</TableHead>
                  <TableHead>From</TableHead>
                  <TableHead>Until</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {rates.rows.map((rate) => (
                  <RateRow
                    key={rate.id}
                    rate={rate}
                    currency={book.currency}
                    canRetire={isAdmin && !pointInTime && rate.valid_to == null}
                    retireHint={
                      !isAdmin
                        ? "Requires the Admin role."
                        : pointInTime
                          ? "Clear the point-in-time view to retire rates."
                          : undefined
                    }
                    onRetire={() => setRetireTarget(rate)}
                  />
                ))}
              </TableBody>
            </Table>
          </div>
          <LoadMore
            shownCount={rates.rows.length}
            hasMore={rates.hasMore}
            isFetchingNextPage={rates.isFetchingNextPage}
            onLoadMore={rates.fetchNextPage}
            noun="rates"
          />
        </Card>
      )}

      <ConfirmDialog
        open={retireTarget !== null}
        onOpenChange={(open) => {
          if (!open) setRetireTarget(null);
        }}
        title="Retire this rate?"
        description={
          retireTarget
            ? `"${retireTarget.measurement_key}" stops pricing new events immediately. Nothing is deleted — this version stays in the book's history, and past events keep their recorded price.`
            : ""
        }
        confirmLabel="Retire rate"
        destructive
        pending={retire.isPending}
        onConfirm={() => {
          if (!retireTarget) return;
          retire.mutate(retireTarget.id, {
            onSuccess: () => {
              toastSuccess("Rate retired", "It remains visible under history.");
              setRetireTarget(null);
            },
            onError: toastOnError("Couldn't retire the rate"),
          });
        }}
      />
    </div>
  );
}

function RateRow({
  rate,
  currency,
  canRetire,
  retireHint,
  onRetire,
}: {
  rate: Rate;
  currency: string;
  canRetire: boolean;
  retireHint: string | undefined;
  onRetire: () => void;
}) {
  const superseded = rate.valid_to != null;
  const dimensionEntries = (
    ["dim1", "dim2", "dim3", "dim4", "dim5", "dim6"] as const
  )
    .map((key) => [key, rate[key]] as const)
    .filter(([, value]) => value !== "");
  return (
    <TableRow className={cn(superseded && "opacity-55")}>
      <TableCell className="font-mono text-[12px]" title={rate.measurement_key}>
        {rate.measurement_key}
      </TableCell>
      <TableCell>
        <div className="flex max-w-[260px] flex-wrap items-center gap-1">
          {rate.provider && <Matcher label="provider" value={rate.provider} />}
          {rate.event_type && <Matcher label="event" value={rate.event_type} />}
          {rate.task_type && <Matcher label="task" value={rate.task_type} />}
          {rate.subtask_type && <Matcher label="subtask" value={rate.subtask_type} />}
          {dimensionEntries.map(([key, value]) => (
            <Badge key={key} variant="outline" className="font-mono text-[10px]">
              {key}={value}
            </Badge>
          ))}
          {!rate.provider &&
            !rate.event_type &&
            !rate.task_type &&
            !rate.subtask_type &&
            dimensionEntries.length === 0 && (
              <span className="text-[11px] text-text-muted">Any event</span>
            )}
        </div>
      </TableCell>
      <TableCell className="text-[12px]">{pricingModelLabel(rate.pricing_model)}</TableCell>
      <TableCell className="text-[12px] whitespace-nowrap">
        {rate.pricing_model === "flat"
          ? "—"
          : formatPrice(rate.rate_per_unit_micros, rate.unit_quantity, undefined, currency)}
      </TableCell>
      <TableCell className="text-[12px] whitespace-nowrap">
        {rate.fixed_micros > 0 ? formatMicros(rate.fixed_micros, currency) : "—"}
      </TableCell>
      <TableCell className="text-[12px] whitespace-nowrap">
        {formatShortDate(rate.valid_from)}
      </TableCell>
      <TableCell className="text-[12px] whitespace-nowrap">
        {rate.valid_to ? (
          <span title={formatDate(rate.valid_to)}>{formatShortDate(rate.valid_to)}</span>
        ) : (
          <Badge variant="secondary">Active</Badge>
        )}
      </TableCell>
      <TableCell className="text-right">
        {rate.valid_to == null && (
          <DisabledHint disabled={!canRetire} hint={retireHint}>
            <Button variant="ghost" size="sm" onClick={onRetire} disabled={!canRetire}>
              Retire
            </Button>
          </DisabledHint>
        )}
      </TableCell>
    </TableRow>
  );
}

function Matcher({ label, value }: { label: string; value: string }) {
  return (
    <span className="text-[11px] text-text-secondary">
      <span className="text-text-muted">{label}=</span>
      <span className="font-mono">{value}</span>
    </span>
  );
}
