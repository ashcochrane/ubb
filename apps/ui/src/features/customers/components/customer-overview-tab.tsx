import { Section, DetailGrid, DetailRow, QueryState } from "@/components/shared/data-states";
import { StatusBadge } from "@/components/shared/status-badge";
import { formatMicros, formatPercent, truncateId } from "@/lib/format";
import { useAuth } from "@/features/auth/hooks/use-auth";
import { CopyField } from "@/components/shared/data-states";
import { useCustomerMargin } from "../api/queries";

/**
 * Identity + a compact financial snapshot assembled from the customer's margin
 * record (the richest single customer-scoped read available).
 */
export function CustomerOverviewTab({
  customerId,
  externalId,
}: {
  customerId: string;
  externalId: string | null;
}) {
  const { isBillingMode } = useAuth();
  const margin = useCustomerMargin(customerId);

  return (
    <div className="space-y-6">
      <Section title="Identity">
        <DetailGrid>
          <DetailRow label="Customer ID">
            <CopyField value={customerId} />
          </DetailRow>
          <DetailRow label="External ID">
            {externalId ? <CopyField value={externalId} /> : <span className="text-muted-foreground">—</span>}
          </DetailRow>
        </DetailGrid>
      </Section>

      {isBillingMode ? (
        <Section title="Financial snapshot" description="Current margin period.">
          <QueryState query={margin}>
            {(m) => (
              <DetailGrid>
                <DetailRow label="Revenue mode">
                  <StatusBadge value={m.revenue_mode} />
                </DetailRow>
                <DetailRow label="Total revenue">{formatMicros(m.total_revenue_micros)}</DetailRow>
                <DetailRow label="Subscription revenue">{formatMicros(m.subscription_revenue_micros)}</DetailRow>
                <DetailRow label="Usage revenue">{formatMicros(m.usage_revenue_micros)}</DetailRow>
                <DetailRow label="Provider cost">{formatMicros(m.provider_cost_micros)}</DetailRow>
                <DetailRow label="Gross margin">
                  {formatMicros(m.gross_margin_micros)}{" "}
                  <span className="text-muted-foreground">({formatPercent(m.margin_percentage)})</span>
                </DetailRow>
                <DetailRow label="Events">{m.event_count.toLocaleString()}</DetailRow>
                <DetailRow label="Period">
                  {m.period.start} → {m.period.end}
                </DetailRow>
              </DetailGrid>
            )}
          </QueryState>
        </Section>
      ) : (
        <Section title="Financial snapshot">
          <p className="text-sm text-muted-foreground">
            Margin data is available when billing is enabled. Customer ref {truncateId(customerId)}.
          </p>
        </Section>
      )}
    </div>
  );
}
