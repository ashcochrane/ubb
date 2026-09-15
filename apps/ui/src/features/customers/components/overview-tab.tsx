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
import type { CustomerMarginOut } from "../api/types";
import { BusinessRollup } from "./business-rollup";

const MarginTrendChart = React.lazy(() => import("./margin-trend-chart"));

export function OverviewTab({
  customerId,
  margin,
  range,
}: {
  customerId: string;
  margin: CustomerMarginOut;
  range: DateRange;
}) {
  const currency = useTenantCurrency();
  const [periods, setPeriods] = React.useState(6);
  const trend = useMarginTrend(customerId, periods);
  const negative = margin.gross_margin_micros < 0;

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
            `${formatEventCount(margin.event_count)} events in window`
          }
        />
        <StatCard
          label="Gross margin"
          value={
            <span className={cn(negative && "text-danger-dark")}>
              {marginBound(margin.gross_margin_micros, margin, currency)}
            </span>
          }
          variant="raised"
          subtitle="Revenue minus provider cost"
        />
        <StatCard
          label="Margin %"
          value={
            <span className={cn(margin.margin_percentage < 0 && "text-danger-dark")}>
              {marginPercentBound(margin.margin_percentage, margin)}
            </span>
          }
          variant="raised"
          // Period bounds are calendar dates — UTC-safe formatting, no raw ISO.
          subtitle={`${formatCalendarDate(margin.period.start)} → ${formatCalendarDate(margin.period.end)}`}
        />
      </div>

      {/* THREE CARDS SINCE #497, AND THEY ADD UP TO THE TOTAL ABOVE. It was
          four: the sources, plus a card saying how much of the billed usage
          counted as revenue. That card existed only because a customer-level
          switch could answer "none of it" — with the switch deleted the two
          usage figures are one figure, and two cards showing the same number
          is worse than one card showing it once. The grid narrows to three
          rather than holding a column open, on the same reasoning #496 used
          when the panel below lost its second card. */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-3">
        <StatCard
          label="Subscription revenue"
          value={formatMicros(margin.subscription_revenue_micros, currency)}
          subtitle="Billed by UBB through Stripe"
        />
        {/* THE CARD THAT MAKES THE TOTAL ABOVE ADD UP (#496). Until slice 7
            this amount was inside the card above it, so a tenant reading
            "subscription revenue" could not tell money UBB had invoiced from
            money it had only been told about. Naming the source is the whole
            point of the record the figure now comes from. */}
        <StatCard
          label="Supplied revenue"
          value={formatMicros(margin.supplied_revenue_micros, currency)}
          subtitle="Stated by you, billed outside UBB"
        />
        <StatCard
          label="Usage billed"
          value={formatMicros(margin.usage_billed_micros, currency)}
          subtitle="Counted as revenue in full"
        />
      </div>

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
        ) : !trend.data || trend.data.points.length === 0 ? (
          <EmptyState
            title="No closed periods yet"
            description="The trend fills in as monthly economics periods close."
          />
        ) : (
          <React.Suspense fallback={<Skeleton className="h-64 w-full" />}>
            <MarginTrendChart points={trend.data.points} currency={currency} />
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

      <BusinessRollup externalId={margin.external_id} range={range} />
    </div>
  );
}
