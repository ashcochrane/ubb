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

import { useCustomerEconomics, useTenantEconomics } from "../api/queries";
import type { Window } from "../api/types";
import { summaryEconomics } from "../lib/economics";

// ⚠ THE METER-ONLY TIP AND ITS TWO RELABELLED CARDS ARE GONE (#501). They said
// a workspace that does not bill through UBB sees what usage WOULD bill at its
// prices rather than revenue — true until #497 deleted the switch that made it
// true, and left standing because the branch keyed on something else. The one
// economic query answers revenue from one definition for every workspace, so
// there is no second reading to label and no second figure to substitute.

export interface StatRowProps {
  window: Window;
  currency: string;
}

export function StatRow({ window, currency }: StatRowProps) {
  const summary = useTenantEconomics(window);
  // Customers WITH USAGE is the row count of the same window grouped by the
  // customer axis — which is what the total that used to publish it as a field
  // was counting. The table below reads the same query, so this costs no
  // second request.
  const customers = useCustomerEconomics(window);

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
        title="Couldn't load this window's economics"
        onRetry={() => void summary.refetch()}
      />
    );
  }

  const view = summaryEconomics(summary.data);

  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
      <StatCard
        variant="raised"
        label="Total revenue"
        value={formatMicros(view.revenue_micros, currency)}
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
      {/* ⚠ A MARGIN UBB CANNOT STATE RENDERS AS AN ABSENCE, NEVER AS ZERO.
          `gross_margin_micros` is nullable on the one query — a margin it
          cannot attribute at the grain asked for has no figure at all — and a
          currency zero here would be exactly the silent zero this surface
          exists to delete. Showing the states as themselves is the rendering
          ticket's; not inventing one is this ticket's. */}
      <StatCard
        variant="raised"
        label="Gross margin"
        value={
          view.margin_micros === null
            ? "—"
            : marginBound(view.margin_micros, summary.data, currency)
        }
        subtitle={
          view.margin_micros === null
            ? "not available for this window"
            : `${marginPercentBound(view.margin_pct, summary.data)} margin`
        }
      />
      {/* ⚠ A COUNT THAT DID NOT ARRIVE IS NOT A COUNT OF NONE. Since the card
          became a SECOND promise (#501) its answer can fail on its own, and
          `data?.length ?? 0` rendered that failure as a workspace with no
          customers — the silent zero the card two along refuses in the same
          grid, arriving here through a query state rather than through a
          measure. The whole row does not fail with it: the four figures beside
          it answered, and a failed refinement is worth less than they are. */}
      {customers.isPending ? (
        <Skeleton className="h-[104px] rounded-md" />
      ) : (
        <StatCard
          variant="raised"
          label="Customers with usage"
          value={
            customers.isError ? "—" : (customers.data?.length ?? 0).toLocaleString()
          }
          subtitle={customers.isError ? "not available for this window" : undefined}
        />
      )}
      <StatCard
        variant="raised"
        label="Events"
        value={
          summary.data.event_count === null
            ? "—"
            : formatEventCount(summary.data.event_count)
        }
      />
    </div>
  );
}
