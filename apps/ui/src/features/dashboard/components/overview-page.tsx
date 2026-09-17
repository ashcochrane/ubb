import * as React from "react";

import { DateRangePicker } from "@/components/shared/date-range-picker";
import { PageHeader } from "@/components/shared/page-header";
import {
  hasProduct,
  useTenantConfig,
  useTenantCurrency,
} from "@/hooks/use-tenant-config";
import { resolveRange, type DateRange } from "@/lib/date-range";

import { eventsOn, onlyRow } from "@/lib/economic-query";

import { useGroupedEconomics, useLifetimeEconomics } from "../api/queries";
import type { BreakdownAxis } from "../api/types";
import { CustomerEconomicsTable } from "./customer-economics-table";
import { GroupingFieldBreakdown } from "./grouping-field-breakdown";
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
  const hasBilling = config ? hasProduct(config, "billing") : false;
  const currency = useTenantCurrency();

  // The windowed question, grouped by the axis the picker names. The stat row
  // asks the same window UNGROUPED for its own totals, which is what lets this
  // one be money-only — a count across rows that mix Event Types is the
  // comparison the server refuses.
  const [groupBy, setGroupBy] = React.useState<BreakdownAxis>("provider");
  const grouped = useGroupedEconomics(window, groupBy);

  // All-time totals decide whether this workspace still looks brand new —
  // deliberately not windowed, so changing the date range never resurrects
  // the getting-started card on an active workspace.
  const lifetime = useLifetimeEconomics();
  const showGettingStarted =
    lifetime.isSuccess && eventsOn(onlyRow(lifetime.data)) === 0;

  return (
    <div className="space-y-5">
      <PageHeader
        title="Overview"
        description="Revenue, provider cost, and margin across your customers."
        actions={<DateRangePicker value={search} onChange={onSearchChange} />}
      />

      {showGettingStarted && <GettingStartedCard needsStripe={hasBilling} />}

      <UnprofitableAlert currency={currency} />

      <StatRow window={window} currency={currency} />

      <RevenueCostSection window={window} currency={currency} />

      <div className="grid gap-5 lg:grid-cols-5">
        <GroupingFieldBreakdown
          className="lg:col-span-2"
          query={grouped}
          groupBy={groupBy}
          onGroupByChange={setGroupBy}
          currency={currency}
        />
        <CustomerEconomicsTable
          className="lg:col-span-3"
          window={window}
          currency={currency}
        />
      </div>
    </div>
  );
}
