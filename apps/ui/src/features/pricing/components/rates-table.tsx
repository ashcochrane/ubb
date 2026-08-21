import * as React from "react";
import { Layers } from "lucide-react";

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
import { cn } from "@/lib/utils";
import { useRates } from "../api/queries";
import { rateStructureLabel } from "../lib/rates";
import type { AnyBook, Rate } from "../api/types";

/**
 * A book's rules: active by default, optional full history, optional
 * point-in-time ("as of") view.
 *
 * ⚠ READ-ONLY SINCE #367. The two immediate routes this table drove — add a
 * rule, retire one — are deleted, because every change to a book is a publish
 * now. The console does not speak the declaring body yet; #372 rebuilds this
 * feature around books, rules and publishes, and until then the way to change
 * a book is the publish dialog beside this table.
 */
export function RatesTable({ book }: { book: AnyBook }) {
  const [includeHistory, setIncludeHistory] = React.useState(false);
  const [asOfLocal, setAsOfLocal] = React.useState("");
  const asOfIso = React.useMemo(() => {
    if (!asOfLocal) return undefined;
    const parsed = new Date(asOfLocal);
    return Number.isNaN(parsed.getTime()) ? undefined : parsed.toISOString();
  }, [asOfLocal]);

  const rates = useRates(book.id, { include_history: includeHistory, as_of: asOfIso });

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
            description="This book prices nothing yet. Rules are added by publishing a change to the book."
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
                </TableRow>
              </TableHeader>
              <TableBody>
                {rates.rows.map((rate) => (
                  <RateRow key={rate.id} rate={rate} currency={rate.currency} />
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
    </div>
  );
}

// ⚠ NO RETIRE ACTION, AND NO ADD (#367). Both immediate routes are deleted:
// a rule is opened and retired by a declared change on a publish now, and the
// console does not speak that body yet — #372 rebuilds this feature around
// books, rules and publishes. Leaving the buttons pointed at deleted routes
// would have been worse than leaving the gap visible.
function RateRow({
  rate,
  currency,
}: {
  rate: Rate;
  currency: string;
}) {
  const superseded = rate.valid_to != null;
  const dimensionEntries = (
    [
      "grouping_field_1",
      "grouping_field_2",
      "grouping_field_3",
      "grouping_field_4",
      "grouping_field_5",
      "grouping_field_6",
      "grouping_field_7",
      "grouping_field_8",
      "grouping_field_9",
      "grouping_field_10",
    ] as const
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
      <TableCell className="text-[12px]">
        {rateStructureLabel(rate.rate_structure)}
      </TableCell>
      <TableCell className="text-[12px] whitespace-nowrap">
        {rate.rate_structure === "fixed_component"
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
