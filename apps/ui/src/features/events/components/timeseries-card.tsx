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
import { GroupingAxisLabel } from "@/components/shared/grouping-axis-label";
import { OpenSetValue } from "@/components/shared/open-set-value";
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
import type { GroupingOption } from "@/lib/grouping-axis";
import { NO_DECLARED_VALUES } from "@/lib/localisation";

import { useUsageTimeseries } from "../api/queries";
import { pivotTimeseries } from "../lib/timeseries";

const UsageTimeseriesChart = lazy(() => import("./usage-timeseries-chart"));

const NO_GROUPING = "none";

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
  const axes = optionsForSurface(useGroupingOptions().data, ANALYTICS_SURFACE);
  const query = useUsageTimeseries({
    ...window,
    customer_id: customerId,
    group_by: groupBy,
  });

  const points = useMemo(() => query.data ?? [], [query.data]);
  const pivot = useMemo(
    () => pivotTimeseries(points, groupBy !== undefined),
    [points, groupBy],
  );

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
              {(value: string) => <SelectedAxis axes={axes} value={value} />}
            </SelectValue>
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={NO_GROUPING}>No grouping</SelectItem>
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
        <div className="flex h-[260px] items-center justify-center text-[13px] text-text-muted">
          No usage recorded in this window.
        </div>
      ) : (
        <Suspense fallback={<Skeleton className="h-[260px] w-full" />}>
          <UsageTimeseriesChart
            data={pivot.data}
            series={pivot.series}
            currency={currency}
          />
        </Suspense>
      )}
    </ChartCard>
  );
}

/** Whatever the picker is currently set to, in words wherever there are any. */
function SelectedAxis({
  axes,
  value,
}: {
  axes: readonly GroupingOption[];
  value: string;
}) {
  if (value === NO_GROUPING) return <>No grouping</>;
  const selected = axes.find((option) => option.key === value);
  if (selected) return <GroupingAxisLabel option={selected} />;
  // Not on offer for this tenant. The chart below is asking for it and the
  // server will say what it thinks; what this must not do is invent a name,
  // so the token shows as itself, marked.
  return <OpenSetValue labelKeys={NO_DECLARED_VALUES} value={value} />;
}
