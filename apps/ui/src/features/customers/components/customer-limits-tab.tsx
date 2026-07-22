import {
  Section,
  DetailGrid,
  DetailRow,
  QueryState,
} from "@/components/shared/data-states";
import { EmptyState } from "@/components/shared/empty-state";
import { StatusBadge } from "@/components/shared/status-badge";
import { formatMicros, formatPercent, humanizeLabel } from "@/lib/format";
import { useBudgetStatus, usePastLimitReport } from "../api/queries";

/** Risk/gating view: current budget consumption and past-limit episodes. */
export function CustomerLimitsTab({ customerId }: { customerId: string }) {
  const status = useBudgetStatus(customerId);
  const report = usePastLimitReport(customerId);

  return (
    <div className="space-y-6">
      <Section title="Budget status" description="Spend against the configured cap this period.">
        <QueryState query={status}>
          {(s) => (
            <DetailGrid>
              <DetailRow label="Period">{s.period}</DetailRow>
              <DetailRow label="Enforcement"><StatusBadge value={s.enforce_mode} /></DetailRow>
              <DetailRow label="Spend">{formatMicros(s.spend_micros)}</DetailRow>
              <DetailRow label="Cap">{formatMicros(s.cap_micros)}</DetailRow>
              <DetailRow label="Consumed">{formatPercent(s.pct)}</DetailRow>
            </DetailGrid>
          )}
        </QueryState>
      </Section>

      <Section
        title="Past-limit report"
        description="Episodes where this customer hit a spend or balance limit."
      >
        <QueryState query={report}>
          {(r) => {
            const totals = Object.entries(r.totals_per_limit ?? {});
            const episodes = Array.isArray(r.episodes) ? r.episodes : [];
            if (totals.length === 0 && episodes.length === 0) {
              return <EmptyState title="No limit episodes" description="This customer hasn't hit any limits in the window." />;
            }
            return (
              <div className="space-y-4">
                {totals.length > 0 && (
                  <DetailGrid>
                    {totals.map(([limit, value]) => (
                      <DetailRow key={limit} label={humanizeLabel(limit)}>
                        {typeof value === "number" ? value.toLocaleString() : String(value)}
                      </DetailRow>
                    ))}
                  </DetailGrid>
                )}
                {episodes.length > 0 && (
                  <p className="text-xs text-muted-foreground">
                    {episodes.length} limit episode{episodes.length === 1 ? "" : "s"} recorded in this window.
                  </p>
                )}
              </div>
            );
          }}
        </QueryState>
      </Section>
    </div>
  );
}
