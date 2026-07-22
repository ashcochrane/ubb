import { Section, QueryState, DetailGrid, DetailRow } from "@/components/shared/data-states";
import { StatusBadge } from "@/components/shared/status-badge";
import { formatMicros } from "@/lib/format";
import { useBudget } from "../api/queries";
import { ViewLink } from "./stat-grid";

export function BudgetSection({ currency }: { currency: string }) {
  const query = useBudget();
  return (
    <Section
      title="Budget"
      description="Tenant-wide spend cap and enforcement."
      actions={<ViewLink to="/billing">View billing</ViewLink>}
    >
      <QueryState query={query}>
        {(b) => (
          <DetailGrid>
            <DetailRow label="Spend cap">{formatMicros(b.cap_micros, currency)}</DetailRow>
            <DetailRow label="Enforcement">
              <StatusBadge value={b.enforce_mode} />
            </DetailRow>
          </DetailGrid>
        )}
      </QueryState>
    </Section>
  );
}
