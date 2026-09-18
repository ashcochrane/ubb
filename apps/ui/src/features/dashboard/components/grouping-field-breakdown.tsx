import { ChartCard } from "@/components/shared/chart-card";
import { ErrorCard } from "@/components/shared/error-card";
import {
  MeasureValue,
  RetentionHorizonNote,
  RevenueContext,
} from "@/components/shared/measure-value";
import { Skeleton } from "@/components/ui/skeleton";
import { CUSTOMER_REVENUE, drawableMeasure, statedValue } from "@/lib/economic-query";
import { ubbAxisTitle } from "@/lib/grouping-axis";
import { measureLabel, readingText, readMeasure } from "@/lib/measure-state";
import { cn } from "@/lib/utils";

import {
  BREAKDOWN_AXES,
  type Breakdown,
  type BreakdownAxis,
} from "../api/types";
import { topWithOther } from "../lib/economics";
import { SectionEmpty } from "./section-empty";

/** The slice of the grouped-economics query result this card consumes. */
export interface AnalyticsQueryLike {
  data: Breakdown | undefined;
  isPending: boolean;
  isError: boolean;
  error: unknown;
  isPlaceholderData?: boolean;
  refetch: () => void;
}

export interface GroupingFieldBreakdownProps {
  query: AnalyticsQueryLike;
  groupBy: BreakdownAxis;
  onGroupByChange: (groupBy: BreakdownAxis) => void;
  currency: string;
  className?: string;
}

export function GroupingFieldBreakdown({
  query,
  groupBy,
  onGroupByChange,
  currency,
  className,
}: GroupingFieldBreakdownProps) {
  return (
    <ChartCard
      title="Cost breakdown"
      className={className}
      actions={
        <div className="flex items-center gap-1" role="group" aria-label="Group cost by">
          {BREAKDOWN_AXES.map((option) => (
            <button
              key={option}
              type="button"
              aria-pressed={option === groupBy}
              onClick={() => onGroupByChange(option)}
              className={cn(
                "h-6 rounded-md px-2 text-[11px] transition-colors",
                option === groupBy
                  ? "bg-primary text-primary-foreground"
                  : "text-text-muted hover:bg-bg-subtle hover:text-text-primary",
              )}
            >
              {ubbAxisTitle(option)}
            </button>
          ))}
        </div>
      }
    >
      <BreakdownBody query={query} groupBy={groupBy} currency={currency} />
    </ChartCard>
  );
}

function BreakdownBody({
  query,
  groupBy,
  currency,
}: {
  query: AnalyticsQueryLike;
  groupBy: BreakdownAxis;
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

  const bars = topWithOther(query.data.rows, 8);
  if (bars.length === 0) {
    // ⚠ AN EMPTY ANSWER IS "NO USAGE" ONLY WHERE THE WINDOW IS INSIDE THE
    // RECORDS IT READS; past their horizon it is a stretch UBB no longer holds.
    return query.data.held_from !== null ? (
      <RetentionHorizonNote caveats={query.data} />
    ) : (
      <SectionEmpty
        title="No usage in this window"
        description="Record events with provider, event type, or product attributes to see cost split here."
        cta={{ label: "Send a test event", to: "/developers" }}
      />
    );
  }

  const plotted = drawableMeasure(query.data.rows);
  const axis = ubbAxisTitle(groupBy).toLowerCase();
  const max = bars.reduce((m, bar) => Math.max(m, statedValue(bar.plotted) ?? 0), 0);
  return (
    <div
      className={cn(
        "space-y-3 transition-opacity",
        query.isPlaceholderData && "opacity-60",
      )}
    >
      {bars.map((bar) => {
        const length = statedValue(bar.plotted);
        return (
          <div key={bar.name}>
            <div className="mb-1 flex items-baseline justify-between gap-3 text-[12px]">
              <span
                className={cn(
                  "truncate",
                  bar.isOther ? "text-text-muted" : "text-text-secondary",
                )}
                title={`${bar.name} — ${readingText(readMeasure(bar.cost, currency))} provider cost`}
              >
                {bar.name}
              </span>
              <span className="shrink-0 font-medium text-text-primary">
                <MeasureValue figure={bar.plotted} currency={currency} />
              </span>
            </div>
            {/* A bar is drawn only for a figure the state states: a gap is not
                a zero-length bar, which would read as "nothing". */}
            <div className="h-1.5 overflow-hidden rounded-full bg-bg-subtle">
              {length !== null && (
                <div
                  className="h-full rounded-full"
                  style={{
                    width: max === 0 ? "0%" : `${Math.max(2, (length / max) * 100)}%`,
                    backgroundColor: bar.isOther ? "var(--chart-3)" : "var(--chart-1)",
                  }}
                />
              )}
            </div>
          </div>
        );
      })}
      {/* The measure the bars turned out to be, by its catalogue word — and,
          where that is the cost, the revenue drawn as its state beside it,
          through the renderer so an unfamiliar state is marked here too. */}
      <p data-plotted-measure={plotted} className="pt-1 text-[11px] text-text-muted">
        {`${measureLabel(plotted)} by ${axis}, top 8 shown.`}
        {plotted !== CUSTOMER_REVENUE && (
          <>
            {` ${measureLabel(CUSTOMER_REVENUE)} by ${axis}: `}
            <MeasureValue figure={bars[0]?.revenue ?? null} currency={currency} />.
          </>
        )}
      </p>
      <RevenueContext context={query.data.context} currency={currency} />
      <RetentionHorizonNote caveats={query.data} />
    </div>
  );
}
