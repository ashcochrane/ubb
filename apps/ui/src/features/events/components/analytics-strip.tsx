// Window totals in both denominations + markup margin, from the analytics
// rollup. Honors the customer scope and the past-limit filters (the API
// composes them into the totals); tag filters apply to the ledger only.

import { ErrorCard } from "@/components/shared/error-card";
import { StatCard } from "@/components/shared/stat-card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatEventCount, formatMicros } from "@/lib/format";
import { useTenantCurrency } from "@/hooks/use-tenant-config";

import { useUsageAnalytics } from "../api/queries";
import type { AnalyticsParams } from "../api/types";

export function AnalyticsStrip({
  params,
  tagFilterActive,
}: {
  params: AnalyticsParams;
  tagFilterActive: boolean;
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
          value={formatEventCount(data.total_events)}
        />
        <StatCard
          variant="raised"
          label="Billed"
          value={formatMicros(data.total_billed_cost_micros, currency)}
        />
        <StatCard
          variant="raised"
          label="Provider cost"
          value={formatMicros(data.total_provider_cost_micros, currency)}
        />
        <StatCard
          variant="raised"
          label="Markup margin"
          value={formatMicros(data.usage_markup_margin_micros, currency)}
          subtitle="Billed minus provider cost"
        />
      </div>
      {tagFilterActive && (
        <p className="text-[11px] text-text-muted">
          Totals cover the window and stop filters — the tag filter applies to
          the table below only.
        </p>
      )}
    </div>
  );
}
