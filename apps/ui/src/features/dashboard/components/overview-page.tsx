import * as React from "react";

import { DateRangePicker } from "@/components/shared/date-range-picker";
import { PageHeader } from "@/components/shared/page-header";
import {
  hasProduct,
  useTenantConfig,
  useTenantCurrency,
} from "@/hooks/use-tenant-config";
import { resolveRange, type DateRange } from "@/lib/date-range";

import { useLifetimeAnalytics, useWindowAnalytics } from "../api/queries";
import type { BreakdownDimension } from "../api/types";
import { CustomerEconomicsTable } from "./customer-economics-table";
import { DimensionBreakdown } from "./dimension-breakdown";
import { GettingStartedCard } from "./getting-started-card";
import { RevenueCostSection } from "./revenue-cost-section";
import { StatRow } from "./stat-row";
import { UnprofitableAlert } from "./unprofitable-alert";

export interface OverviewPageProps {
  search: DateRange;
  onSearchChange: (next: DateRange) => void;
}

/**
 * The CFO overview: operational + unit-economics summary for the current
 * date window (URL-backed, defaults to month-to-date).
 */
export function OverviewPage({ search, onSearchChange }: OverviewPageProps) {
  const window = resolveRange(search);
  const { data: config } = useTenantConfig();
  const meterOnly = config?.billing_mode === "meter_only";
  const hasBilling = config ? hasProduct(config, "billing") : false;
  const currency = useTenantCurrency();

  // One windowed analytics query powers both the events stat and the
  // cost-by-dimension card (totals are dimension-independent).
  const [dimension, setDimension] = React.useState<BreakdownDimension>("provider");
  const analytics = useWindowAnalytics(window, dimension);

  // All-time totals decide whether this workspace still looks brand new —
  // deliberately not windowed, so changing the date range never resurrects
  // the getting-started card on an active workspace.
  const lifetime = useLifetimeAnalytics();
  const showGettingStarted =
    lifetime.isSuccess && lifetime.data.total_events === 0;

  return (
    <div className="space-y-5">
      <PageHeader
        title="Overview"
        description="Revenue, provider cost, and margin across your customers."
        actions={<DateRangePicker value={search} onChange={onSearchChange} />}
      />

      {showGettingStarted && <GettingStartedCard needsStripe={hasBilling} />}

      <UnprofitableAlert currency={currency} />

      <StatRow
        window={window}
        meterOnly={meterOnly}
        currency={currency}
        eventsTotal={analytics.data?.total_events}
        eventsPending={analytics.isPending}
      />

      <RevenueCostSection window={window} meterOnly={meterOnly} currency={currency} />

      <div className="grid gap-5 lg:grid-cols-5">
        <DimensionBreakdown
          className="lg:col-span-2"
          query={analytics}
          dimension={dimension}
          onDimensionChange={setDimension}
          currency={currency}
        />
        <CustomerEconomicsTable
          className="lg:col-span-3"
          window={window}
          meterOnly={meterOnly}
          currency={currency}
        />
      </div>
    </div>
  );
}
