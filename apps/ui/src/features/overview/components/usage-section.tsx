import { Section, QueryState } from "@/components/shared/data-states";
import { StatCard } from "@/components/shared/stat-card";
import { formatEventCount, formatMicros } from "@/lib/format";
import { useUsageAnalytics } from "../api/queries";
import { lastNDays } from "../lib/date-range";
import { StatGrid, ViewLink } from "./stat-grid";

export function UsageSection({ currency }: { currency: string }) {
  const query = useUsageAnalytics(lastNDays(30));
  return (
    <Section
      title="Usage"
      description="Metered events and billed usage over the last 30 days."
      actions={<ViewLink to="/usage">View usage</ViewLink>}
    >
      <QueryState query={query}>
        {(u) => (
          <StatGrid>
            <StatCard variant="raised" label="Total events" value={formatEventCount(u.total_events)} />
            <StatCard
              variant="raised"
              label="Total billed"
              value={formatMicros(u.total_billed_cost_micros, currency)}
              subtitle="What you bill customers"
            />
            <StatCard
              variant="raised"
              label="Markup margin"
              value={formatMicros(u.usage_markup_margin_micros, currency)}
              subtitle="Billed minus provider cost"
            />
          </StatGrid>
        )}
      </QueryState>
    </Section>
  );
}
