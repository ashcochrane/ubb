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
  MarginShare,
  MeasureValue,
  RetentionHorizonNote,
} from "@/components/shared/measure-value";
import { statedValue } from "@/lib/economic-query";
import { formatCalendarDate } from "@/lib/format";
import {
  figureNote,
  isNegative,
  noFigureNote,
  readingText,
  readMeasure,
} from "@/lib/measure-state";
import { revenueBasisNote } from "@/lib/supplied-revenue";
import { cn } from "@/lib/utils";

import { useMarginTrend } from "../api/queries";
import type { CustomerEconomics } from "../api/types";
import { BusinessRollup } from "./business-rollup";
import { RevenuePanels } from "./revenue-panels";

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
  // neither and rendered as its state below.
  const negative = isNegative(margin.margin);

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard
          label="Total revenue"
          value={<MeasureValue figure={margin.revenue} currency={currency} />}
          variant="raised"
          // THE SUBTITLE NAMED THE DELETED SWITCH UNTIL #497 — "Resolved
          // revenue mode: …" — which told a reader which rule had been applied
          // to their own usage rather than what the number was made of. The
          // three sources are the honest answer, and they are the row below.
          subtitle={
            figureNote(margin.revenue, currency) ??
            "Subscriptions, supplied figures and billed usage"
          }
          // ⚠ THE SUPPLIED SHARE IS NOT SPLIT OUT HERE AND IS NOT MEANT TO BE.
          // The one economic query answers `customer_revenue` from ONE
          // definition (#501) and publishes no split; what the panels below
          // show is the supplied RECORD's own figures, read from the record
          // that owns them, which is a different question from "how much of
          // this total was supplied".
        />
        {/* The cost card's subtitle already carries a count — the events in
            the window — so the one that says how many of them went uncosted
            replaces it while it has something to say. Two counts on one card
            is where a reader stops reading either. */}
        <StatCard
          label="Provider cost (COGS)"
          value={<MeasureValue figure={margin.cost} currency={currency} />}
          variant="raised"
          subtitle={
            figureNote(margin.cost, currency) ??
            (statedValue(margin.events) === null
              ? undefined
              : `${readingText(readMeasure(margin.events, currency))} events in window`)
          }
        />
        <StatCard
          label="Gross margin"
          value={
            <span className={cn(negative && "text-danger-dark")}>
              <MeasureValue figure={margin.margin} currency={currency} />
            </span>
          }
          variant="raised"
          subtitle={noFigureNote(margin.margin, currency) ?? "Revenue minus provider cost"}
        />
        <StatCard
          label="Margin %"
          value={
            <span className={cn(negative && "text-danger-dark")}>
              <MarginShare margin={margin.margin} revenue={margin.revenue} />
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
        ) : !trend.data || trend.data.points.length === 0 ? (
          trend.data && trend.data.held_from !== null ? (
            <RetentionHorizonNote caveats={trend.data} />
          ) : (
            <EmptyState
              title="No closed periods yet"
              description="The trend fills in as monthly economics periods close."
            />
          )
        ) : (
          <>
            <React.Suspense fallback={<Skeleton className="h-64 w-full" />}>
              <MarginTrendChart points={trend.data.points} currency={currency} />
            </React.Suspense>
            <RetentionHorizonNote caveats={trend.data} />
            {/* ⚠ **THE REVENUE LINE INCLUDES SUPPLIED AMOUNTS, AND ONE OF THE
                TWO VIEWS SPREADS THEM (§5).** A figure a tenant stated for a
                quarter appears in three months under `recognised` and in one
                under `recorded` — so a trend drawn without saying which is a
                chart the reader cannot interpret, and the smoothing is exactly
                the kind "they did not ask for". The answer names the view it
                served; this is the console repeating it rather than assuming
                one. */}
            <p data-revenue-basis={trend.data.basis} className="mt-2 text-[11px] text-text-muted">
              {revenueBasisNote(trend.data.basis)}
            </p>
          </>
        )}
      </ChartCard>

      {/* THE REVENUE PANELS ARE BACK IN THIS SLOT (#508, slice 7 section 9),
          and they are a different pair from the two #496 and #497 deleted.
          Those wrote a recurring amount with no period and set a
          customer-level switch; these READ the tenant-supplied revenue record
          under a basis the reader chooses, and WRITE one period at a time with
          its own source reference. The mid-period affordance section 9 rules
          into this slice is the day field on the form. */}
      <RevenuePanels customerId={customerId} range={range} />

      <BusinessRollup externalId={externalId} range={range} />
    </div>
  );
}
