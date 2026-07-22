import { useMemo, useState } from "react";
import { Plus, CheckSquare } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { StatCard } from "@/components/shared/stat-card";
import {
  Section,
  LoadingRows,
  ErrorInline,
  ProductUnavailable,
} from "@/components/shared/data-states";
import { formatMicros, formatEventCount } from "@/lib/format";
import { useAuth } from "@/features/auth/hooks/use-auth";
import { useUsageAnalytics, useUsageTimeseries } from "../api/queries";
import { BreakdownTable, DefensiveTable } from "./breakdown-table";
import { UsageEventsExplorer } from "./usage-events-explorer";
import { RecordUsageDialog } from "./record-usage-dialog";
import { CloseTaskDialog } from "./close-task-dialog";

/** YYYY-MM-DD for `d` days ago (0 = today), for <input type="date">. */
function isoDaysAgo(days: number): string {
  const d = new Date();
  d.setDate(d.getDate() - days);
  return d.toISOString().slice(0, 10);
}

export function UsagePage() {
  const { hasProduct } = useAuth();
  const [startDate, setStartDate] = useState(() => isoDaysAgo(30));
  const [endDate, setEndDate] = useState(() => isoDaysAgo(0));

  const params = useMemo(
    () => ({ start_date: startDate, end_date: endDate }),
    [startDate, endDate],
  );
  const analytics = useUsageAnalytics(params);
  const timeseries = useUsageTimeseries({ ...params, granularity: "day" });

  if (!hasProduct("metering")) return <ProductUnavailable product="Metering" />;

  const actions = (
    <div className="flex items-center gap-2">
      <CloseTaskDialog
        trigger={
          <Button variant="outline" size="sm">
            <CheckSquare />
            Close task
          </Button>
        }
      />
      <RecordUsageDialog
        trigger={
          <Button size="sm">
            <Plus />
            Record usage
          </Button>
        }
      />
    </div>
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title="Usage"
        description="Metered usage, costs, and margin across your customers."
        actions={actions}
      />

      <div className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">
          Start date
          <Input
            type="date"
            value={startDate}
            max={endDate}
            onChange={(e) => setStartDate(e.target.value)}
            className="w-auto"
          />
        </label>
        <label className="flex flex-col gap-1 text-xs text-muted-foreground">
          End date
          <Input
            type="date"
            value={endDate}
            min={startDate}
            onChange={(e) => setEndDate(e.target.value)}
            className="w-auto"
          />
        </label>
      </div>

      {analytics.isLoading ? (
        <LoadingRows />
      ) : analytics.isError ? (
        <ErrorInline error={analytics.error} onRetry={analytics.refetch} />
      ) : analytics.data ? (
        <div className="space-y-6">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard
              label="Total events"
              value={formatEventCount(analytics.data.total_events)}
            />
            <StatCard
              label="Billed (customer charge)"
              value={formatMicros(analytics.data.total_billed_cost_micros)}
            />
            <StatCard
              label="Provider cost"
              value={formatMicros(analytics.data.total_provider_cost_micros)}
            />
            <StatCard
              label="Markup margin"
              value={formatMicros(analytics.data.usage_markup_margin_micros)}
            />
          </div>
          <p className="text-xs text-muted-foreground">
            <span className="font-medium text-foreground">Provider cost</span> is what
            upstream providers charged you.{" "}
            <span className="font-medium text-foreground">Billed</span> is what you charged
            customers.{" "}
            <span className="font-medium text-foreground">Markup margin</span> is billed
            minus provider cost — your gross profit on usage.
          </p>

          <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
            <BreakdownTable title="By provider" rows={analytics.data.by_provider} />
            <BreakdownTable title="By event type" rows={analytics.data.by_event_type} />
            <BreakdownTable title="By customer" rows={analytics.data.by_customer} />
            <BreakdownTable title="By product" rows={analytics.data.by_product} />
          </div>
        </div>
      ) : null}

      <Section
        title="Usage over time"
        description="Time series of usage for the selected range (daily granularity)."
      >
        {timeseries.isLoading ? (
          <LoadingRows rows={4} />
        ) : timeseries.isError ? (
          <ErrorInline error={timeseries.error} onRetry={timeseries.refetch} />
        ) : (
          <DefensiveTable
            rows={timeseries.data?.series ?? []}
            emptyMessage="No usage recorded in the selected range."
          />
        )}
      </Section>

      <UsageEventsExplorer />
    </div>
  );
}
