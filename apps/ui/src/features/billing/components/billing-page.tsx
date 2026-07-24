import { PageHeader } from "@/components/shared/page-header";
import { ProductGate } from "@/components/shared/product-gate";
import { useTenantConfig } from "@/hooks/use-tenant-config";
import type { DateRange } from "@/lib/date-range";

import { AdjustmentsCard } from "./adjustments-card";
import { BudgetCard } from "./budget-card";
import { PostpaidConfigCard } from "./postpaid-config-card";
import { RevenueSection } from "./revenue-section";
import { UsageInvoicesCard } from "./usage-invoices-card";

export interface BillingPageProps {
  /** URL-backed revenue window (start_date/end_date). */
  search: DateRange;
  onSearchChange: (next: DateRange) => void;
}

export function BillingPage({ search, onSearchChange }: BillingPageProps) {
  const { data: config } = useTenantConfig();

  return (
    <ProductGate product="billing">
      <div className="space-y-6">
        <PageHeader
          title="Billing"
          description="Workspace-level billing: revenue, the monthly budget, customer usage invoices, and manual ledger adjustments."
        />
        <RevenueSection range={search} onRangeChange={onSearchChange} />
        <BudgetCard />
        <UsageInvoicesCard />
        {config?.billing_mode === "postpaid" && <PostpaidConfigCard />}
        <AdjustmentsCard />
      </div>
    </ProductGate>
  );
}
