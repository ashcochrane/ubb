import * as React from "react";

import { ChartCard } from "@/components/shared/chart-card";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorCard } from "@/components/shared/error-card";
import { StatCard } from "@/components/shared/stat-card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useTenantCurrency } from "@/hooks/use-tenant-config";
import type { DateRange } from "@/lib/date-range";
import {
  formatCalendarDate,
  formatEventCount,
  formatMicros,
} from "@/lib/format";
import {
  marginBound,
  marginPercentBound,
  partialTotalNote,
  supplierCostTotal,
} from "@/lib/supplier-cost";
import { cn } from "@/lib/utils";

import { useMarginTrend } from "../api/queries";
import type { CustomerEconomics } from "../api/types";
import { BusinessRollup } from "./business-rollup";

const MarginTrendChart = React.lazy(() => import("./margin-trend-chart"));

export function OverviewTab({
  customerId,
  margin,
  externalId,
  range,
}: {
  customerId: string;
  margin: CustomerEconomics;
  /** The tenant's own id for this customer, from the identity read —
   *  the margin no longer carries one (#501). */
  externalId: string;
  range: DateRange;
}) {
  const currency = useTenantCurrency();
  const [periods, setPeriods] = React.useState(6);
  const trend = useMarginTrend(customerId, periods);
  // ⚠ AN ABSENT MARGIN IS NEITHER NEGATIVE NOR ZERO, so it is styled as
  // neither and rendered as an absence below.
  const negative =
    margin.gross_margin_micros !== null && margin.gross_margin_micros < 0;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard
          label="Total revenue"
          value={formatMicros(margin.total_revenue_micros, currency)}
          variant="raised"
          // THE SUBTITLE NAMED THE DELETED SWITCH UNTIL #497 — "Resolved
          // revenue mode: …" — which told a reader which rule had been applied
          // to their own usage rather than what the number was made of. The
          // three sources are the honest answer, and they are the row below.
          subtitle="Subscriptions, supplied figures and billed usage"
        />
        {/* The cost card's subtitle already carries a count — the events in
            the window — so the one that says how many of them went uncosted
            replaces it while it has something to say. Two counts on one card
            is where a reader stops reading either. */}
        <StatCard
          label="Provider cost (COGS)"
          value={supplierCostTotal(margin.provider_cost_micros, margin, currency)}
          variant="raised"
          subtitle={
            partialTotalNote(margin.unresolved_event_count) ??
            (margin.event_count === null
              ? undefined
              : `${formatEventCount(margin.event_count)} events in window`)
          }
        />
        <StatCard
          label="Gross margin"
          value={
            <span className={cn(negative && "text-danger-dark")}>
              {margin.gross_margin_micros === null
                ? "—"
                : marginBound(margin.gross_margin_micros, margin, currency)}
            </span>
          }
          variant="raised"
          subtitle="Revenue minus provider cost"
        />
        <StatCard
          label="Margin %"
          value={
            <span className={cn(margin.margin_percentage < 0 && "text-danger-dark")}>
              {margin.gross_margin_micros === null
                ? "—"
                : marginPercentBound(margin.margin_percentage, margin)}
            </span>
          }
          variant="raised"
          // Period bounds are calendar dates — UTC-safe formatting, no raw ISO.
          subtitle={`${formatCalendarDate(range.start_date ?? "")} → ${formatCalendarDate(range.end_date ?? "")}`}
        />
      </div>

      {/* ⚠ THE THREE REVENUE-SOURCE CARDS ARE GONE (#501), AND THE REASON IS
          THE COLLAPSE RATHER THAN A DESIGN CHANGE. They split the total above
          into a subscription share, a figure the tenant supplied and billed
          usage — three fields of one customer's margin. The one economic query
          answers `customer_revenue` from ONE definition, which is the whole
          point of it, and publishes no split.

          The supplied share is still readable, from the record that owns it
          (`GET /margin/customers/{id}/supplied-revenue`, which states the basis
          it was attributed on and the source reference behind it). Rebuilding
          this panel on that read — and on whatever answers the subscription
          share — is the customers feature's own ticket; inventing a split here
          from figures the server no longer separates would be worse than not
          showing one. */}
      <ChartCard
        title="Margin trend (closed monthly periods)"
        actions={
          <Select
            value={String(periods)}
            onValueChange={(value) => {
              if (value !== null) setPeriods(Number(value));
            }}
          >
            <SelectTrigger className="h-7 text-[12px]" aria-label="Trend periods">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="6">Last 6 periods</SelectItem>
              <SelectItem value="12">Last 12 periods</SelectItem>
            </SelectContent>
          </Select>
        }
      >
        {trend.isLoading ? (
          <Skeleton className="h-64 w-full" />
        ) : trend.isError ? (
          <ErrorCard error={trend.error} onRetry={() => void trend.refetch()} />
        ) : !trend.data || trend.data.length === 0 ? (
          <EmptyState
            title="No closed periods yet"
            description="The trend fills in as monthly economics periods close."
          />
        ) : (
          <React.Suspense fallback={<Skeleton className="h-64 w-full" />}>
            <MarginTrendChart points={trend.data} currency={currency} />
          </React.Suspense>
        )}
      </ChartCard>

      {/* THE REVENUE PANELS WERE RENDERED HERE AND ARE GONE (#497,
          slice 7 section 9). The module held two cards; #496 deleted the
          recurring-amount card with the record it wrote, and this ticket
          deletes the revenue-mode card with the switch it set, which left
          nothing to render. #508 puts the supplied-revenue write panel
          back in this slot, with the mid-period affordance section 9
          rules into this slice. An empty grid held open for it would be a
          defect on every customer page in the meantime. */}

      <BusinessRollup externalId={externalId} range={range} />
    </div>
  );
}
