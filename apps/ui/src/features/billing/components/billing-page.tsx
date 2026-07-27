import { PageHeader } from "@/components/shared/page-header";
import { ProductUnavailable } from "@/components/shared/data-states";
import { useAuth } from "@/features/auth/hooks/use-auth";
import { RevenueSection } from "./revenue-section";
import { BudgetSection } from "./budget-section";
import { PostpaidSection } from "./postpaid-section";
import { ManualAdjustmentsSection } from "./manual-adjustments-section";
import { PreCheckSection } from "./precheck-section";

export function BillingPage() {
  const { isBillingMode } = useAuth();

  return (
    <div className="space-y-6">
      <PageHeader
        title="Billing"
        description="Tenant revenue, spend budget, postpaid push, and manual wallet adjustments."
      />
      {isBillingMode ? (
        <>
          <RevenueSection />
          <BudgetSection />
          <PostpaidSection />
          <ManualAdjustmentsSection />
          <PreCheckSection />
        </>
      ) : (
        <ProductUnavailable product="Billing" />
      )}
    </div>
  );
}
