import { ChartCard } from "@/components/shared/chart-card";
import { ErrorCard } from "@/components/shared/error-card";
import { Skeleton } from "@/components/ui/skeleton";
import { formatEventCount, formatMicros } from "@/lib/format";
import { dimensionLabel } from "@/lib/labels";
import { cn } from "@/lib/utils";

import {
  BREAKDOWN_DIMENSIONS,
  toBreakdownRows,
  type BreakdownDimension,
  type UsageAnalytics,
} from "../api/types";
import { topWithOther } from "../lib/economics";
import { SectionEmpty } from "./section-empty";

/** The slice of the analytics query result this card consumes. */
export interface AnalyticsQueryLike {
  data: UsageAnalytics | undefined;
  isPending: boolean;
  isError: boolean;
  error: unknown;
  isPlaceholderData?: boolean;
  refetch: () => void;
}

export interface DimensionBreakdownProps {
  query: AnalyticsQueryLike;
  dimension: BreakdownDimension;
  onDimensionChange: (dimension: BreakdownDimension) => void;
  currency: string;
  className?: string;
}

export function DimensionBreakdown({
  query,
  dimension,
  onDimensionChange,
  currency,
  className,
}: DimensionBreakdownProps) {
  return (
    <ChartCard
      title="Cost by dimension"
      className={className}
      actions={
        <div className="flex items-center gap-1" role="group" aria-label="Breakdown dimension">
          {BREAKDOWN_DIMENSIONS.map((option) => (
            <button
              key={option}
              type="button"
              aria-pressed={option === dimension}
              onClick={() => onDimensionChange(option)}
              className={cn(
                "h-6 rounded-md px-2 text-[11px] transition-colors",
                option === dimension
                  ? "bg-primary text-primary-foreground"
                  : "text-text-muted hover:bg-bg-subtle hover:text-text-primary",
              )}
            >
              {dimensionLabel(option)}
            </button>
          ))}
        </div>
      }
    >
      <BreakdownBody query={query} dimension={dimension} currency={currency} />
    </ChartCard>
  );
}

function BreakdownBody({
  query,
  dimension,
  currency,
}: {
  query: AnalyticsQueryLike;
  dimension: BreakdownDimension;
  currency: string;
}) {
  if (query.isPending) {
    return (
      <div className="space-y-3">
        {Array.from({ length: 6 }, (_, i) => (
          <Skeleton key={i} className="h-7 rounded" />
        ))}
      </div>
    );
  }
  if (query.isError) {
    return (
      <ErrorCard
        error={query.error}
        title="Couldn't load the breakdown"
        onRetry={() => query.refetch()}
      />
    );
  }
  if (!query.data) return null;

  const bars = topWithOther(toBreakdownRows(query.data, dimension), 8);
  if (bars.length === 0) {
    return (
      <SectionEmpty
        title="No usage in this window"
        description="Record events with provider, event type, or product attributes to see cost split here."
        cta={{ label: "Send a test event", to: "/developers" }}
      />
    );
  }

  const max = bars.reduce((m, bar) => Math.max(m, bar.billed_micros), 0);
  return (
    <div
      className={cn(
        "space-y-3 transition-opacity",
        query.isPlaceholderData && "opacity-60",
      )}
    >
      {bars.map((bar) => (
        <div key={bar.name}>
          <div className="mb-1 flex items-baseline justify-between gap-3 text-[12px]">
            <span
              className={cn(
                "truncate",
                bar.isOther ? "text-text-muted" : "text-text-secondary",
              )}
              title={`${bar.name} — ${formatEventCount(bar.event_count)} events`}
            >
              {bar.name}
            </span>
            <span className="shrink-0 font-medium text-text-primary">
              {formatMicros(bar.billed_micros, currency)}
            </span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-bg-subtle">
            <div
              className="h-full rounded-full"
              style={{
                width: max === 0 ? "0%" : `${Math.max(2, (bar.billed_micros / max) * 100)}%`,
                backgroundColor: bar.isOther ? "var(--chart-3)" : "var(--chart-1)",
              }}
            />
          </div>
        </div>
      ))}
      <p className="pt-1 text-[11px] text-text-muted">
        Billed cost by {dimensionLabel(dimension).toLowerCase()}, top 8 shown.
      </p>
    </div>
  );
}
