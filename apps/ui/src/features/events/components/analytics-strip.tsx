// Window totals in both denominations + gross margin, from the one economic
// query (#501 — and the margin card's own note below says why that figure is no
// longer "markup margin"). Honors the customer scope and the past-limit filters
// (the API composes them into the totals); the metadata filter applies to the
// ledger only.

import { ErrorCard } from "@/components/shared/error-card";
import { MeasureValue } from "@/components/shared/measure-value";
import { StatCard } from "@/components/shared/stat-card";
import { Skeleton } from "@/components/ui/skeleton";
import { figureNote, isNegative, noFigureNote } from "@/lib/measure-state";
import { cn } from "@/lib/utils";
import { useTenantCurrency } from "@/hooks/use-tenant-config";

import { useUsageAnalytics } from "../api/queries";
import type { AnalyticsParams } from "../api/types";

export function AnalyticsStrip({
  params,
  metadataFilterActive,
}: {
  params: AnalyticsParams;
  metadataFilterActive: boolean;
}) {
  const currency = useTenantCurrency();
  const analytics = useUsageAnalytics(params);

  if (analytics.isLoading) {
    return (
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {Array.from({ length: 4 }, (_, index) => (
          <Skeleton key={index} className="h-[92px] w-full rounded-md" />
        ))}
      </div>
    );
  }

  if (analytics.isError) {
    return (
      <ErrorCard
        error={analytics.error}
        onRetry={() => void analytics.refetch()}
        title="Couldn't load usage totals"
      />
    );
  }

  const data = analytics.data;
  if (!data) return null;

  return (
    <div className="space-y-1.5">
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {/* ⚠ EVERY FIGURE ON THE STRIP IS DRAWN AS ITS STATE ALLOWS (#510).
            The narrowing coalesced the count, the revenue and the cost to
            zero, so a window reaching back past the economic horizon read
            "0 events" and "$0.00" here. */}
        <StatCard
          variant="raised"
          label="Events"
          value={<MeasureValue figure={data.events} currency={currency} />}
        />
        <StatCard
          variant="raised"
          label="Revenue"
          value={<MeasureValue figure={data.revenue} currency={currency} />}
          subtitle={figureNote(data.revenue, currency)}
        />
        <StatCard
          variant="raised"
          label="Provider cost"
          value={<MeasureValue figure={data.cost} currency={currency} />}
          subtitle={figureNote(data.cost, currency)}
        />
        {/* ⚠ "MARKUP MARGIN" WAS NEITHER (#501) — it was the difference
            between two aggregates, named as if it were a rate. It is the
            gross-margin measure now, drawn as its state allows. */}
        <StatCard
          variant="raised"
          label="Gross margin"
          value={
            <span className={cn(isNegative(data.margin) && "text-destructive")}>
              <MeasureValue figure={data.margin} currency={currency} />
            </span>
          }
          subtitle={noFigureNote(data.margin, currency) ?? "Revenue minus provider cost"}
        />
      </div>
      {metadataFilterActive && (
        <p className="text-[11px] text-text-muted">
          Totals cover the window and stop filters — the metadata filter applies
          to the table below only.
        </p>
      )}
    </div>
  );
}
