import { PageHeader } from "@/components/shared/page-header";
import { useAuth } from "@/features/auth/hooks/use-auth";
import { SetupChecklistSection } from "./setup-checklist-section";
import { MarginSummarySection } from "./margin-summary-section";
import { RevenueSection } from "./revenue-section";
import { UsageSection } from "./usage-section";
import { UnprofitableSection } from "./unprofitable-section";
import { WebhooksHealthSection } from "./webhooks-health-section";
import { BudgetSection } from "./budget-section";

export function OverviewPage() {
  const { tenantName, isBillingMode, hasProduct, defaultCurrency } = useAuth();
  const showMetering = hasProduct("metering");

  return (
    <div className="space-y-6">
      <PageHeader
        title={tenantName ? `Overview — ${tenantName}` : "Overview"}
        description="Operational summary of your account."
      />

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
        {/* Always-on: account readiness. */}
        <div className="xl:col-span-2">
          <SetupChecklistSection />
        </div>

        {isBillingMode && (
          <div className="xl:col-span-2">
            <MarginSummarySection currency={defaultCurrency} />
          </div>
        )}

        {isBillingMode && <RevenueSection currency={defaultCurrency} />}
        {showMetering && <UsageSection currency={defaultCurrency} />}

        {isBillingMode && (
          <div className="xl:col-span-2">
            <UnprofitableSection currency={defaultCurrency} />
          </div>
        )}

        <WebhooksHealthSection />
        {isBillingMode && <BudgetSection currency={defaultCurrency} />}
      </div>
    </div>
  );
}
