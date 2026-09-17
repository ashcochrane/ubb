// Window totals in both denominations + gross margin, from the one economic
// query (#501 — and the margin card's own note below says why that figure is no
// longer "markup margin"). Honors the customer scope and the past-limit filters
// (the API composes them into the totals); the metadata filter applies to the
// ledger only.

import { ErrorCard } from "@/components/shared/error-card";
import { StatCard } from "@/components/shared/stat-card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatEventCount, formatMicros } from "@/lib/format";
import {
  marginBound,
  partialTotalNote,
  supplierCostTotal,
} from "@/lib/supplier-cost";
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
        <StatCard
          variant="raised"
          label="Events"
          value={formatEventCount(data.event_count)}
        />
        <StatCard
          variant="raised"
          label="Revenue"
          value={formatMicros(data.revenue_micros, currency)}
        />
        <StatCard
          variant="raised"
          label="Provider cost"
          value={supplierCostTotal(
            data.provider_cost_micros,
            data,
            currency,
          )}
          subtitle={partialTotalNote(data.unresolved_event_count) ?? undefined}
        />
        {/* ⚠ "MARKUP MARGIN" WAS NEITHER (#501) — it was the difference
            between two aggregates, named as if it were a rate. It is the
            gross-margin measure now, and a window UBB cannot state one for
            renders as an absence rather than as zero. */}
        <StatCard
          variant="raised"
          label="Gross margin"
          value={
            data.margin_micros === null
              ? "—"
              : marginBound(data.margin_micros, data, currency)
          }
          subtitle="Revenue minus provider cost"
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
