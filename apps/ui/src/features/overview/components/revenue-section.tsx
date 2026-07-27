import { Section, QueryState } from "@/components/shared/data-states";
import { StatCard } from "@/components/shared/stat-card";
import { formatMicros } from "@/lib/format";
import { useRevenueAnalytics } from "../api/queries";
import { lastNDays } from "../lib/date-range";
import { StatGrid, ViewLink } from "./stat-grid";

export function RevenueSection({ currency }: { currency: string }) {
  const query = useRevenueAnalytics(lastNDays(30));
  return (
    <Section
      title="Revenue"
      description="Cost, customer charge, and markup over the last 30 days."
      actions={<ViewLink to="/billing">View billing</ViewLink>}
    >
      <QueryState query={query}>
        {(r) => (
          <StatGrid>
            <StatCard
              variant="raised"
              label="Provider cost"
              value={formatMicros(r.total_provider_cost_micros, currency)}
              subtitle="What providers charge you"
            />
            <StatCard
              variant="raised"
              label="Customer charge"
              value={formatMicros(r.total_billed_cost_micros, currency)}
              subtitle="What you bill customers"
            />
            <StatCard
              variant="raised"
              label="Platform markup"
              value={formatMicros(r.total_markup_micros, currency)}
              subtitle="Charge minus cost"
            />
          </StatGrid>
        )}
      </QueryState>
    </Section>
  );
}
