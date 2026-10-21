import * as React from "react";
import { Tag } from "lucide-react";

import { EmptyState } from "@/components/shared/empty-state";
import { ErrorCard } from "@/components/shared/error-card";
import { LoadMore } from "@/components/shared/load-more";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
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
import { formatDate, formatExactMicros, formatShortDate, type ExactMicros } from "@/lib/format";
import { useTenantCurrency } from "@/hooks/use-tenant-config";
import { tenantDefinedLabel } from "@/lib/localisation";
import { cn } from "@/lib/utils";
import { useAgreedPrices } from "../api/queries";
import type { AgreedPrice, PricingBook } from "../api/types";

/**
 * A Pricing Book's agreed prices (#553): what one delivered unit of each kind
 * of work sells for — the open lines by default, every version with history.
 *
 * ⚠ **IT READS AND DOES NOT WRITE**, for the reason the rules table beside it
 * gives: an agreed price is added, repriced and retired by declaring a change
 * and publishing it, so a row action here would be a second mutation surface
 * for an act that has one.
 *
 * The price is shown to the micro: an agreed price may be below a cent, and a
 * cent-rounded figure would show two different prices as one. A line opening
 * in the future is open and not yet in force, and says so beside its date.
 */
export function AgreedPricesTable({ book }: { book: PricingBook }) {
  const [includeHistory, setIncludeHistory] = React.useState(false);
  const prices = useAgreedPrices(book.id, { include_history: includeHistory });
  // The tenant's one currency, which a Charge is raised in: an agreed price
  // carries none of its own (USD micros, no FX — #553).
  const currency = useTenantCurrency();

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-[14px] font-semibold text-text-primary">Agreed prices</h2>
        <div className="flex items-center gap-2">
          <Switch
            checked={includeHistory}
            onCheckedChange={setIncludeHistory}
            aria-label="Include agreed-price history"
          />
          <Label>Include history</Label>
        </div>
      </div>
      <p className="text-[11px] text-text-muted">
        One price per delivered run of a kind of work sold at one agreed price. A
        run pins the price in force when it starts, so a reprice reaches the runs
        started after it and never one already running.
      </p>

      {prices.isInitialLoading ? (
        <Card size="sm" className="p-3">
          <div className="space-y-2">
            <Skeleton className="h-8 w-full" />
            <Skeleton className="h-8 w-full" />
          </div>
        </Card>
      ) : prices.isError ? (
        <ErrorCard
          error={prices.error}
          onRetry={() => void prices.refetch()}
          title="Couldn't load this book's agreed prices"
        />
      ) : prices.rows.length === 0 ? (
        <EmptyState
          icon={Tag}
          title="No agreed prices"
          description={
            includeHistory
              ? "This book has never held an agreed price."
              : "This book sells no kind of work at one agreed price. Declare a change to add one."
          }
        />
      ) : (
        <Card size="sm" className="gap-0 py-0">
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Kind of work</TableHead>
                  <TableHead>Agreed price</TableHead>
                  <TableHead>From</TableHead>
                  <TableHead>Until</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {prices.rows.map((line) => (
                  <AgreedPriceRow key={line.id} line={line} currency={currency} />
                ))}
              </TableBody>
            </Table>
          </div>
          <LoadMore
            shownCount={prices.rows.length}
            hasMore={prices.hasMore}
            isFetchingNextPage={prices.isFetchingNextPage}
            onLoadMore={prices.fetchNextPage}
            noun="agreed prices"
          />
        </Card>
      )}
    </div>
  );
}

/** Open and not yet in force: the line opens at a moment still ahead (#553). */
function opensLater(line: AgreedPrice): boolean {
  return new Date(line.valid_from).getTime() > Date.now();
}

function AgreedPriceRow({ line, currency }: { line: AgreedPrice; currency: string }) {
  const closed = line.valid_to != null;
  const scheduled = !closed && opensLater(line);
  return (
    <TableRow className={cn(closed && "opacity-55")}>
      <TableCell className="font-mono text-[12px]">{tenantDefinedLabel(line.task_type)}</TableCell>
      <TableCell className="text-[12px] whitespace-nowrap">
        {formatExactMicros(String(line.agreed_price_micros) as ExactMicros, currency)}
      </TableCell>
      <TableCell className="text-[12px] whitespace-nowrap">
        <span title={formatDate(line.valid_from)}>{formatShortDate(line.valid_from)}</span>
      </TableCell>
      <TableCell className="text-[12px] whitespace-nowrap">
        {line.valid_to ? (
          <span title={formatDate(line.valid_to)}>{formatShortDate(line.valid_to)}</span>
        ) : scheduled ? (
          <Badge variant="outline">Scheduled</Badge>
        ) : (
          <Badge variant="secondary">Active</Badge>
        )}
      </TableCell>
    </TableRow>
  );
}
