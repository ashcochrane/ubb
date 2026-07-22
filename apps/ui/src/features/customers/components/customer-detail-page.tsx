import { useMemo, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { ArrowLeft } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { TabBar, type TabDef } from "@/components/shared/tabs";
import { useAuth } from "@/features/auth/hooks/use-auth";
import { useCustomerMargin } from "../api/queries";
import { CustomerOverviewTab } from "./customer-overview-tab";
import { CustomerWalletTab } from "./customer-wallet-tab";
import { CustomerPricingTab } from "./customer-pricing-tab";
import { CustomerUsageTab } from "./customer-usage-tab";
import { CustomerMarginTab } from "./customer-margin-tab";
import { CustomerSubscriptionTab } from "./customer-subscription-tab";
import { CustomerLimitsTab } from "./customer-limits-tab";

/**
 * Customer detail. There is no single-customer GET endpoint, so identity is
 * assembled from the customer-scoped views (margin, wallet, usage, …). The
 * external_id — needed for subscription lifecycle — is resolved from margin
 * data when billing is enabled.
 */
export function CustomerDetailPage({ customerId }: { customerId: string }) {
  const navigate = useNavigate();
  const { hasProduct, isBillingMode } = useAuth();
  const [tab, setTab] = useState("overview");

  // Margin carries the external_id needed for subscription lifecycle actions.
  const margin = useCustomerMargin(customerId);
  const externalId = margin.data?.external_id ?? null;

  const tabs = useMemo<TabDef[]>(() => {
    const t: TabDef[] = [{ value: "overview", label: "Overview" }];
    if (isBillingMode) t.push({ value: "wallet", label: "Wallet" });
    if (hasProduct("metering")) {
      t.push({ value: "pricing", label: "Pricing" });
      t.push({ value: "usage", label: "Usage" });
    }
    if (isBillingMode) t.push({ value: "margin", label: "Margin" });
    if (hasProduct("subscriptions")) t.push({ value: "subscription", label: "Subscription" });
    if (isBillingMode) t.push({ value: "limits", label: "Limits" });
    return t;
  }, [hasProduct, isBillingMode]);

  const active = tabs.some((t) => t.value === tab) ? tab : "overview";

  return (
    <div className="space-y-6">
      <PageHeader
        title="Customer"
        description={customerId}
        actions={
          <Button variant="ghost" size="sm" onClick={() => navigate({ to: "/customers" })}>
            <ArrowLeft />
            Back
          </Button>
        }
      />

      <TabBar tabs={tabs} value={active} onChange={setTab} />

      {active === "overview" && <CustomerOverviewTab customerId={customerId} externalId={externalId} />}
      {active === "wallet" && <CustomerWalletTab customerId={customerId} />}
      {active === "pricing" && <CustomerPricingTab customerId={customerId} />}
      {active === "usage" && <CustomerUsageTab customerId={customerId} />}
      {active === "margin" && <CustomerMarginTab customerId={customerId} />}
      {active === "subscription" && (
        <CustomerSubscriptionTab customerId={customerId} externalId={externalId} />
      )}
      {active === "limits" && <CustomerLimitsTab customerId={customerId} />}
    </div>
  );
}
