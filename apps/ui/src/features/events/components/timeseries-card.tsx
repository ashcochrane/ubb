// Daily cost chart with an optional group-by axis. Painted series are
// capped at 3 (monochrome discipline) — extra groups fold into "Other".

import { lazy, Suspense, useMemo } from "react";

import { ChartCard } from "@/components/shared/chart-card";
import { ChartLegend } from "@/components/shared/chart-legend";
import { ErrorCard } from "@/components/shared/error-card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useTenantCurrency } from "@/hooks/use-tenant-config";
import { dimensionLabel, TIMESERIES_GROUP_BY } from "@/lib/labels";

import { useUsageTimeseries } from "../api/queries";
import { asTimeseriesPoints } from "../api/types";
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
  const query = useUsageTimeseries({
    ...window,
    customer_id: customerId,
    group_by: groupBy,
  });

  const points = useMemo(
    () => asTimeseriesPoints(query.data?.series ?? []),
    [query.data],
  );
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
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={NO_GROUPING}>No grouping</SelectItem>
            {TIMESERIES_GROUP_BY.map((option) => (
              <SelectItem key={option} value={option}>
                By {dimensionLabel(option).toLowerCase()}
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
