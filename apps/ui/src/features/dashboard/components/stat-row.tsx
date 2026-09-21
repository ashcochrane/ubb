import { ErrorCard } from "@/components/shared/error-card";
import { MeasureValue } from "@/components/shared/measure-value";
import { StatCard } from "@/components/shared/stat-card";
import { Skeleton } from "@/components/ui/skeleton";
import { ABSENT_LABEL } from "@/lib/localisation";
import { figureNote, isNegative, shareNote } from "@/lib/measure-state";
import { cn } from "@/lib/utils";

import { useCustomerEconomics, useTenantEconomics } from "../api/queries";
import type { Window } from "../api/types";

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

  const totals = summary.data;

  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
      {/* ⚠ EVERY FIGURE ON THIS ROW IS DRAWN AS ITS STATE ALLOWS (#510). The
          narrowing used to coalesce each amount to zero, so a window reaching
          back past the economic horizon read "$0.00" on the cost and revenue
          cards; `MeasureValue` draws the state instead, and the subtitle says
          why — a bound's count, or the sentence a state with no figure owes. */}
      <StatCard
        variant="raised"
        label="Total revenue"
        value={<MeasureValue figure={totals.revenue} currency={currency} />}
        subtitle={figureNote(totals.revenue, currency)}
      />
      {/* The window's supplier cost is a FLOOR wherever the summary counts
          events it could not cost, and the margin beside it is then a ceiling
          — the same count, read from its other side. */}
      <StatCard
        variant="raised"
        label="Provider cost (COGS)"
        value={<MeasureValue figure={totals.cost} currency={currency} />}
        subtitle={figureNote(totals.cost, currency)}
      />
      {/* ⚠ A MARGIN UBB CANNOT STATE RENDERS AS ITS STATE, NEVER AS ZERO — and
          its state is the query's, derived from BOTH sides (§15), so an
          uncosted event makes it a bound even where the revenue reads known. */}
      <StatCard
        variant="raised"
        label="Gross margin"
        value={
          <span className={cn(isNegative(totals.margin) && "text-destructive")}>
            <MeasureValue figure={totals.margin} currency={currency} />
          </span>
        }
        subtitle={shareNote(totals.margin, totals.revenue, currency)}
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
            customers.isError
              ? ABSENT_LABEL
              : (customers.data?.length ?? 0).toLocaleString()
          }
          subtitle={
            customers.isError ? "not available for this window" : undefined
          }
        />
      )}
      <StatCard
        variant="raised"
        label="Events"
        value={<MeasureValue figure={totals.events} currency={currency} />}
      />
    </div>
  );
}
