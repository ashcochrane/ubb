import * as React from "react";
import { Link } from "@tanstack/react-router";
import { ArrowUpRight } from "lucide-react";

import { ChartCard } from "@/components/shared/chart-card";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorCard } from "@/components/shared/error-card";
import { StatCard } from "@/components/shared/stat-card";
import { buttonVariants } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useTenantCurrency } from "@/hooks/use-tenant-config";
import type { DateRange } from "@/lib/date-range";
import { formatEventCount, formatMicros } from "@/lib/format";
import {
  marginBound,
  partialTotalNote,
  supplierCostTotal,
} from "@/lib/supplier-cost";
import { cn } from "@/lib/utils";

import { useUsageAnalytics, useUsageTimeseries } from "../api/queries";

const UsageTimeseriesChart = React.lazy(() => import("./usage-timeseries-chart"));

export function UsageTab({
  customerId,
  range,
  stopsAndBreaches,
}: {
  customerId: string;
  range: DateRange;
  /**
   * Stops and breaches, filtered to this customer — the spend-controls
   * feature's component, injected by the route (#466). One rendering, two
   * hosts: the Spend controls tab renders it tenant-wide and this tab renders
   * the same component with the customer fixed. It is injected rather than
   * imported because a feature may not import another's components; a tab
   * missing its injection renders nothing in the section's place rather than
   * a second copy of the report.
   */
  stopsAndBreaches?: React.ReactNode;
}) {
  const currency = useTenantCurrency();
  const analytics = useUsageAnalytics(customerId, range);
  const timeseries = useUsageTimeseries(customerId, range);

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        {/* Typed router Link (SPA navigation) — eventsSearchSchema accepts customer_id. */}
        <Link
          to="/events"
          search={{ customer_id: customerId }}
          className={buttonVariants({ variant: "outline", size: "sm" })}
        >
          Open in events ledger <ArrowUpRight data-icon="inline-end" />
        </Link>
      </div>

      {analytics.isLoading ? (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {Array.from({ length: 4 }, (_, index) => (
            <Skeleton key={index} className="h-24 w-full" />
          ))}
        </div>
      ) : analytics.isError ? (
        <ErrorCard error={analytics.error} onRetry={() => void analytics.refetch()} />
      ) : analytics.data ? (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <StatCard
            label="Events"
            value={formatEventCount(analytics.data.event_count ?? 0)}
            variant="raised"
          />
          <StatCard
            label="Billed cost"
            value={formatMicros(analytics.data.total_revenue_micros, currency)}
            variant="raised"
          />
          <StatCard
            label="Provider cost"
            value={supplierCostTotal(
              analytics.data.provider_cost_micros,
              analytics.data,
              currency,
            )}
            variant="raised"
            subtitle={
              partialTotalNote(analytics.data.unresolved_event_count) ?? undefined
            }
          />
          <StatCard
            label="Markup margin"
            value={
              <span
                className={cn(
                  (analytics.data.gross_margin_micros ?? 0) < 0 && "text-danger-dark",
                )}
              >
                {marginBound(
                  (analytics.data.gross_margin_micros ?? 0),
                  analytics.data,
                  currency,
                )}
              </span>
            }
            variant="raised"
            subtitle="Billed minus provider cost"
          />
        </div>
      ) : null}

      <ChartCard title="Daily spend">
        {timeseries.isLoading ? (
          <Skeleton className="h-56 w-full" />
        ) : timeseries.isError ? (
          <ErrorCard error={timeseries.error} onRetry={() => void timeseries.refetch()} />
        ) : !timeseries.data || timeseries.data.length === 0 ? (
          <EmptyState
            title="No usage in this window"
            description="Recorded events will chart here by day."
          />
        ) : (
          <React.Suspense fallback={<Skeleton className="h-56 w-full" />}>
            <UsageTimeseriesChart
              points={timeseries.data}
              currency={currency}
            />
          </React.Suspense>
        )}
      </ChartCard>

      {stopsAndBreaches}
    </div>
  );
}
