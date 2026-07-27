import { ErrorCard } from "@/components/shared/error-card";
import { StatCard } from "@/components/shared/stat-card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatEventCount, formatMicros, formatPercent } from "@/lib/format";

import { useMarginSummary } from "../api/queries";
import type { Window } from "../api/types";
import { summaryEconomics } from "../lib/economics";
import { HelpTip } from "./help-tip";

const METERED_TIP =
  "This workspace is meter-only: UBB tracks what usage would bill at your " +
  "prices (usage billed) but doesn't count it as revenue until a customer " +
  "is switched to billed mode. Provider cost is real either way.";

export interface StatRowProps {
  window: Window;
  meterOnly: boolean;
  currency: string;
  /** Event total from the windowed analytics query (owned by the page). */
  eventsTotal: number | undefined;
  eventsPending: boolean;
}

export function StatRow({
  window,
  meterOnly,
  currency,
  eventsTotal,
  eventsPending,
}: StatRowProps) {
  const summary = useMarginSummary(window);

  if (summary.isPending) {
    return (
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        {Array.from({ length: 5 }, (_, i) => (
          <Skeleton key={i} className="h-[104px] rounded-md" />
        ))}
      </div>
    );
  }
  if (summary.isError) {
    return (
      <ErrorCard
        error={summary.error}
        title="Couldn't load the margin summary"
        onRetry={() => void summary.refetch()}
      />
    );
  }

  const view = summaryEconomics(summary.data, meterOnly);
  const revenueLabel = meterOnly ? "Usage billed (metered)" : "Total revenue";
  const marginLabel = meterOnly ? "Usage margin (metered)" : "Gross margin";

  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
      <StatCard
        variant="raised"
        label={revenueLabel}
        value={
          <span className="inline-flex items-baseline gap-1.5">
            {formatMicros(view.revenue_micros, currency)}
            {meterOnly && <HelpTip label="About usage billed" text={METERED_TIP} />}
          </span>
        }
      />
      <StatCard
        variant="raised"
        label="Provider cost (COGS)"
        value={formatMicros(summary.data.provider_cost_micros, currency)}
      />
      <StatCard
        variant="raised"
        label={marginLabel}
        value={
          <span className="inline-flex items-baseline gap-1.5">
            {formatMicros(view.margin_micros, currency)}
            {meterOnly && <HelpTip label="About usage margin" text={METERED_TIP} />}
          </span>
        }
        subtitle={`${formatPercent(view.margin_pct)} margin`}
      />
      <StatCard
        variant="raised"
        label="Customers with usage"
        value={summary.data.customer_count.toLocaleString()}
      />
      {eventsPending ? (
        <Skeleton className="h-[104px] rounded-md" />
      ) : (
        <StatCard
          variant="raised"
          label="Events"
          value={eventsTotal === undefined ? "—" : formatEventCount(eventsTotal)}
        />
      )}
    </div>
  );
}
