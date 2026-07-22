import { useState } from "react";
import { PageHeader } from "@/components/shared/page-header";
import { ProductUnavailable, Section } from "@/components/shared/data-states";
import { TabBar, useTabs } from "@/components/shared/tabs";
import { FormField } from "@/components/shared/form-field";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/features/auth/hooks/use-auth";
import {
  BillingPeriodsList,
  TenantInvoicesList,
  UsageInvoicesList,
} from "./invoice-lists";

const TABS = [
  { value: "usage", label: "Usage invoices" },
  { value: "tenant", label: "Tenant invoices" },
  { value: "periods", label: "Billing periods" },
];

function UsageInvoicesTab() {
  const { isBillingMode } = useAuth();
  const [draft, setDraft] = useState("");
  const [period, setPeriod] = useState<string | undefined>(undefined);

  if (!isBillingMode) return <ProductUnavailable product="Billing" />;

  return (
    <Section
      title="Customer usage invoices"
      description="Per-customer metered usage rolled up for Stripe push. Filter by billing period."
      actions={
        <form
          className="flex items-end gap-2"
          onSubmit={(e) => {
            e.preventDefault();
            setPeriod(draft.trim() || undefined);
          }}
        >
          <FormField label="Period" className="w-48">
            {(id) => (
              <Input
                id={id}
                placeholder="e.g. 2026-07"
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
              />
            )}
          </FormField>
        </form>
      }
    >
      {/* Remount on filter change so cursor paging restarts cleanly. */}
      <UsageInvoicesList key={period ?? "all"} period={period} />
    </Section>
  );
}

export function InvoicesPage() {
  const { active, setActive } = useTabs(TABS);

  return (
    <div className="space-y-6">
      <PageHeader
        title="Invoices"
        description="Usage invoices, platform-fee tenant invoices, and billing periods."
      />
      <TabBar tabs={TABS} value={active} onChange={setActive} />
      {active === "usage" && <UsageInvoicesTab />}
      {active === "tenant" && (
        <Section
          title="Tenant invoices"
          description="Platform-fee invoices issued to this tenant."
        >
          <TenantInvoicesList />
        </Section>
      )}
      {active === "periods" && (
        <Section
          title="Billing periods"
          description="Accrued usage cost and platform fee per billing period."
        >
          <BillingPeriodsList />
        </Section>
      )}
    </div>
  );
}
