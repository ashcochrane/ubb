import { PageHeader } from "@/components/shared/page-header";
import { ProductGate } from "@/components/shared/product-gate";
import { holdsAWallet, useTenantConfig } from "@/hooks/use-tenant-config";
import type { DateRange } from "@/lib/date-range";

import { AdjustmentsCard } from "./adjustments-card";
import { CustomerSpendPoolCard } from "./customer-spend-pool-card";
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
          description="Workspace-level billing: revenue, the customer spend pool default for seats, customer usage invoices, and manual ledger adjustments."
        />
        <RevenueSection range={search} onRangeChange={onSearchChange} />
        <CustomerSpendPoolCard />
        <UsageInvoicesCard />
        {config?.billing_mode === "postpaid" && <PostpaidConfigCard />}
        {/* Manual credit and debit are wallet-only writes (R10 Stage C5, F-12):
            rendered only where the workspace's billing mode keeps a wallet,
            never probed for the 403 the route answers off the wallet lane. */}
        {holdsAWallet(config) && <AdjustmentsCard />}
      </div>
    </ProductGate>
  );
}
