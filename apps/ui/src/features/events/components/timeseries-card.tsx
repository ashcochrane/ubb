// Daily cost chart with an optional group-by axis. Painted series are
// capped at 3 (monochrome discipline) — extra groups fold into "Other".
//
// ⚠ **THE AXIS LIST IS THIS TENANT'S, NOT THIS CONSOLE'S (#506).** It used to
// be five names written into `@/lib/labels` — two real axes and `dim1`-`dim3`,
// the physical slots, offered to every workspace whether or not it had declared
// anything at all. It is now the discovery contract's answer for the workspace
// looking at it, so a second tenant opening this card sees a different list,
// each axis marked as a column or a join.

import { lazy, Suspense, useMemo } from "react";

import { ChartCard } from "@/components/shared/chart-card";
import { ChartLegend } from "@/components/shared/chart-legend";
import { ErrorCard } from "@/components/shared/error-card";
import {
  GroupingAxisLabel,
  SelectedGroupingAxis,
} from "@/components/shared/grouping-axis-label";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  ANALYTICS_SURFACE,
  optionsForSurface,
  useGroupingOptions,
} from "@/hooks/use-grouping-options";
import { useTenantCurrency } from "@/hooks/use-tenant-config";

import {
  RetentionHorizonNote,
  RevenueContext,
} from "@/components/shared/measure-value";
import { CUSTOMER_REVENUE, SUPPLIER_COGS } from "@/lib/economic-query";
import { readingText, readMeasure } from "@/lib/measure-state";
import type { AnalyticsMeasure } from "@/lib/vocabulary";

import { useUsageTimeseries } from "../api/queries";
import type { TimeseriesPoint } from "../api/types";
import { groupedMeasuresFor, pivotTimeseries } from "../lib/timeseries";

/**
 * What a grouped chart's lines are, in words — and, where it draws the cost
 * because the revenue could not be placed, what the revenue reads instead.
 */
function plottedCaption(
  plotted: AnalyticsMeasure,
  points: readonly TimeseriesPoint[],
  currency: string,
): string {
  if (plotted === CUSTOMER_REVENUE) return "Lines are revenue by group, per day.";
  if (plotted === SUPPLIER_COGS) {
    return `Lines are provider cost by group, per day. Revenue by group: ${readingText(
      readMeasure(points[0]?.revenue ?? null, currency),
    )}.`;
  }
  return "Lines are recorded events by group, per day — this axis answers no money.";
}

const UsageTimeseriesChart = lazy(() => import("./usage-timeseries-chart"));

const NO_GROUPING = "none";
const NO_GROUPING_LABEL = "No grouping";

export function TimeseriesCard({
  window,
  customerId,
  groupBy,
  onGroupByChange,
}: {
  window: { start_date: string; end_date: string };
  customerId?: string;
  groupBy?: string;
  onGroupByChange: (groupBy: string | undefined) => void;
}) {
  const currency = useTenantCurrency();
  // ⚠ NO SKELETON AND NO ERROR CARD ON THE AXIS LIST, WHICH IS A CHOICE. While
  // the discovery contract is in flight, or if it fails, the picker offers only
  // "No grouping" — and the card it heads goes on rendering the ungrouped
  // answer, which is the thing a reader came for. Grouping is a refinement, so
  // failing the whole chart over the list of refinements available would be a
  // worse answer than showing the chart. What it must never do is state
  // something false, and an empty list does not: it offers nothing rather than
  // claiming this tenant has nothing.
  const axes = optionsForSurface(useGroupingOptions().data, ANALYTICS_SURFACE);
  // What the chosen axis answers, off its own discovery entry — so picking the
  // measurement-concept rollup asks for the count it answers rather than the
  // money it refuses (#510). An axis the list does not (yet) hold refuses
  // nothing we know of, which is the ordinary case.
  const chosen = axes.find((option) => option.key === groupBy);
  const measures = groupBy === undefined
    ? undefined
    : groupedMeasuresFor(chosen?.unsupported_measures ?? []);
  const query = useUsageTimeseries({
    ...window,
    customer_id: customerId,
    group_by: groupBy,
    ...(measures === undefined ? {} : { measures }),
  });

  const points = useMemo(() => query.data?.points ?? [], [query.data]);
  const pivot = useMemo(
    () => pivotTimeseries(points, groupBy !== undefined),
    [points, groupBy],
  );
  const caveats = query.data;

  return (
    <ChartCard
      title="Daily cost"
      legend={
        pivot.series.length >= 2 && pivot.data.length > 0 ? (
          <ChartLegend
            variant="line"
            items={pivot.series.map((entry) => ({
              label: entry.label,
              color: entry.color,
            }))}
          />
        ) : undefined
      }
      actions={
        <Select
          value={groupBy ?? NO_GROUPING}
          onValueChange={(value) =>
            onGroupByChange(
              typeof value === "string" && value !== NO_GROUPING
                ? value
                : undefined,
            )
          }
        >
          <SelectTrigger
            className="h-7 w-[150px] text-[12px]"
            aria-label="Group chart by"
          >
            {/* ⚠ RENDERED, NOT ECHOED. Left to itself this trigger prints the
                raw VALUE, which under the retired vocabulary was a bare axis
                name and is now a whole request word — `rollup:event_category`
                in the chart's own header. The selected row is looked up and
                worded like every row in the list below, and an axis this
                tenant does not offer (a bookmark from before it was retired,
                or another workspace's) falls to the open-set rule rather than
                to a word that would be a guess. */}
            <SelectValue>
              {(value: string) => (
                <SelectedGroupingAxis
                  axes={axes}
                  value={value}
                  none={{ value: NO_GROUPING, label: NO_GROUPING_LABEL }}
                />
              )}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={NO_GROUPING}>{NO_GROUPING_LABEL}</SelectItem>
            {axes.map((option) => (
              <SelectItem key={option.key} value={option.key}>
                <GroupingAxisLabel option={option} />
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      }
    >
      {query.isLoading ? (
        <Skeleton className="h-[260px] w-full" />
      ) : query.isError ? (
        <ErrorCard
          error={query.error}
          onRetry={() => void query.refetch()}
          title="Couldn't load the timeseries"
        />
      ) : pivot.data.length === 0 ? (
        // ⚠ "NO USAGE" ONLY WHERE THE WINDOW IS INSIDE THE RECORDS IT READS
        // (#510). A grouping by what was measured over a stretch whose
        // measurement records were pruned answers NO ROWS — there is nothing
        // left to group — and this line used to call that "no usage". It is a
        // pruned series, and it says so.
        <div className="flex h-[260px] items-center justify-center px-6 text-center text-[13px] text-text-muted">
          {caveats && caveats.held_from !== null ? (
            <RetentionHorizonNote caveats={caveats} />
          ) : (
            "No usage recorded in this window."
          )}
        </div>
      ) : (
        <div className="space-y-1.5">
          <Suspense fallback={<Skeleton className="h-[260px] w-full" />}>
            <UsageTimeseriesChart
              data={pivot.data}
              series={pivot.series}
              plotted={pivot.plotted}
              currency={currency}
            />
          </Suspense>
          {groupBy !== undefined && (
            <p className="text-[11px] text-text-muted">{plottedCaption(pivot.plotted, points, currency)}</p>
          )}
          {caveats && <RevenueContext context={caveats.context} currency={currency} />}
          {caveats && <RetentionHorizonNote caveats={caveats} />}
        </div>
      )}
    </ChartCard>
  );
}

