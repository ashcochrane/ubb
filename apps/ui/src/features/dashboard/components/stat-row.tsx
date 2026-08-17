import { ErrorCard } from "@/components/shared/error-card";
import { StatCard } from "@/components/shared/stat-card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatEventCount, formatMicros } from "@/lib/format";
import {
  marginBound,
  marginPercentBound,
  partialTotalNote,
  supplierCostTotal,
} from "@/lib/supplier-cost";

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
      {/* The window's supplier cost is a FLOOR wherever the summary counts
          events it could not cost, and the margin beside it is then a ceiling
          — the same count, read from its other side. The note sits on the cost
          card alone: it explains both, and repeating it would make a caveat out
          of something that is one fact. */}
      <StatCard
        variant="raised"
        label="Provider cost (COGS)"
        value={supplierCostTotal(
          summary.data.provider_cost_micros,
          summary.data,
          currency,
        )}
        subtitle={partialTotalNote(summary.data.unresolved_event_count) ?? undefined}
      />
      <StatCard
        variant="raised"
        label={marginLabel}
        value={
          <span className="inline-flex items-baseline gap-1.5">
            {marginBound(view.margin_micros, summary.data, currency)}
            {meterOnly && <HelpTip label="About usage margin" text={METERED_TIP} />}
          </span>
        }
        subtitle={`${marginPercentBound(view.margin_pct, summary.data)} margin`}
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
