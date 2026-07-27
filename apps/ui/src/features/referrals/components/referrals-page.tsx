import { PageHeader } from "@/components/shared/page-header";
import { ProductGate } from "@/components/shared/product-gate";

import { AnalyticsSection } from "./analytics-section";
import { PayoutExportCard } from "./payout-export-card";
import { ProgramSection } from "./program-section";
import { ReferrersSection } from "./referrers-section";

export function ReferralsPage({
  onOpenReferrer,
}: {
  onOpenReferrer: (customerId: string) => void;
}) {
  return (
    <ProductGate product="referrals">
      <div className="space-y-6">
        <PageHeader
          title="Referrals"
          description="Reward customers for the customers they bring — attribution, rewards, and payout exports."
        />
        <ProgramSection />
        <AnalyticsSection onOpenReferrer={onOpenReferrer} />
        <ReferrersSection onOpenReferrer={onOpenReferrer} />
        <PayoutExportCard />
      </div>
    </ProductGate>
  );
}
