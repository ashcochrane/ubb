import { StatCard } from "@/components/shared/stat-card";
import { Section, QueryState } from "@/components/shared/data-states";
import { DetailGrid, DetailRow } from "@/components/shared/data-states";
import { formatMicros, formatPercent, formatShortDate } from "@/lib/format";
import { useMarginSummary } from "../api/queries";
import type { DateRange } from "../api/types";

export function SummaryTab({
  range,
  currency,
}: {
  range: DateRange;
  currency: string;
}) {
  const query = useMarginSummary(range);

  return (
    <QueryState query={query}>
      {(summary) => (
        <div className="space-y-6">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <StatCard
              label="Total revenue"
              value={formatMicros(summary.total_revenue_micros, currency)}
            />
            <StatCard
              label="Gross margin"
              value={formatMicros(summary.gross_margin_micros, currency)}
            />
            <StatCard
              label="Margin %"
              value={formatPercent(summary.margin_percentage)}
            />
            <StatCard
              label="Provider cost"
              value={formatMicros(summary.provider_cost_micros, currency)}
            />
            <StatCard label="Customers" value={summary.customer_count} />
          </div>

          <Section
            title="Revenue breakdown"
            description={`Period ${formatShortDate(summary.period.start)} — ${formatShortDate(summary.period.end)}. Gross margin is total revenue minus provider cost.`}
          >
            <DetailGrid>
              <DetailRow label="Subscription revenue">
                {formatMicros(summary.subscription_revenue_micros, currency)}
              </DetailRow>
              <DetailRow label="Usage revenue (billed to customers)">
                {formatMicros(summary.usage_revenue_micros, currency)}
              </DetailRow>
              <DetailRow label="Usage billed">
                {formatMicros(summary.usage_billed_micros, currency)}
              </DetailRow>
              <DetailRow label="Provider cost (what you pay)">
                {formatMicros(summary.provider_cost_micros, currency)}
              </DetailRow>
            </DetailGrid>
          </Section>
        </div>
      )}
    </QueryState>
  );
}
