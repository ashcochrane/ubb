import { Section, QueryState } from "@/components/shared/data-states";
import { StatCard } from "@/components/shared/stat-card";
import { formatMicros, formatPercent } from "@/lib/format";
import { useMarginSummary } from "../api/queries";
import { lastNDays } from "../lib/date-range";
import { StatGrid, ViewLink } from "./stat-grid";

export function MarginSummarySection({ currency }: { currency: string }) {
  const query = useMarginSummary(lastNDays(30));
  return (
    <Section
      title="Margin"
      description="Revenue and gross margin over the last 30 days."
      actions={<ViewLink to="/margin">View margin</ViewLink>}
    >
      <QueryState query={query}>
        {(m) => (
          <StatGrid>
            <StatCard variant="raised" label="Total revenue" value={formatMicros(m.total_revenue_micros, currency)} />
            <StatCard variant="raised" label="Gross margin" value={formatMicros(m.gross_margin_micros, currency)} />
            <StatCard variant="raised" label="Margin %" value={formatPercent(m.margin_percentage)} />
            <StatCard variant="raised" label="Provider cost" value={formatMicros(m.provider_cost_micros, currency)} subtitle="What providers charge you" />
            <StatCard variant="raised" label="Customers" value={m.customer_count.toLocaleString()} />
          </StatGrid>
        )}
      </QueryState>
    </Section>
  );
}
