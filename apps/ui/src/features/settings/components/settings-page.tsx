import { useAuth } from "@/features/auth/hooks/use-auth";
import { PageHeader } from "@/components/shared/page-header";
import { TabBar, useTabs, type TabDef } from "@/components/shared/tabs";
import { LoadingRows } from "@/components/shared/data-states";
import { GeneralTab } from "./general-tab";
import { ProductsTab } from "./products-tab";
import { ApiKeysTab } from "./api-keys-tab";
import { TeamTab } from "./team-tab";
import { StripeTab } from "./stripe-tab";
import { SandboxTab } from "./sandbox-tab";

const TABS: TabDef[] = [
  { value: "general", label: "General" },
  { value: "products", label: "Products" },
  { value: "api-keys", label: "API keys" },
  { value: "team", label: "Team" },
  { value: "stripe", label: "Stripe" },
  { value: "sandbox", label: "Sandbox" },
];

export function SettingsPage() {
  const auth = useAuth();
  const { active, setActive } = useTabs(TABS);
  const config = auth.tenant;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Settings"
        description="Manage your tenant's configuration, products, keys, team, and integrations."
      />
      <TabBar tabs={TABS} value={active} onChange={setActive} />

      {(active === "general" || active === "products") && !config ? (
        <LoadingRows />
      ) : (
        <>
          {active === "general" && config && <GeneralTab config={config} />}
          {active === "products" && config && <ProductsTab config={config} />}
          {active === "api-keys" && <ApiKeysTab />}
          {active === "team" && <TeamTab />}
          {active === "stripe" && <StripeTab />}
          {active === "sandbox" && <SandboxTab />}
        </>
      )}
    </div>
  );
}
