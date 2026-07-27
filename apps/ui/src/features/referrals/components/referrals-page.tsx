import { PageHeader } from "@/components/shared/page-header";
import { ProductUnavailable } from "@/components/shared/data-states";
import { TabBar, useTabs } from "@/components/shared/tabs";
import { useAuth } from "@/features/auth/hooks/use-auth";
import { ProgramTab } from "./program-tab";
import { ReferrersTab } from "./referrers-tab";
import { AnalyticsTab } from "./analytics-tab";
import { PayoutsTab } from "./payouts-tab";

const TABS = [
  { value: "program", label: "Program" },
  { value: "referrers", label: "Referrers" },
  { value: "analytics", label: "Analytics" },
  { value: "payouts", label: "Payouts" },
];

export function ReferralsPage() {
  const { hasProduct } = useAuth();
  const { active, setActive } = useTabs(TABS);

  if (!hasProduct("referrals")) {
    return (
      <div className="space-y-6">
        <PageHeader title="Referrals" />
        <ProductUnavailable product="Referrals" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Referrals"
        description="Reward customers for bringing in new ones — configure the program, enrol referrers, and track earnings."
      />
      <TabBar tabs={TABS} value={active} onChange={setActive} />

      {active === "program" && <ProgramTab />}
      {active === "referrers" && <ReferrersTab />}
      {active === "analytics" && <AnalyticsTab />}
      {active === "payouts" && <PayoutsTab />}
    </div>
  );
}
