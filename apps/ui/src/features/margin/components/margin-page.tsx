import { useState } from "react";
import { PageHeader } from "@/components/shared/page-header";
import { ProductUnavailable } from "@/components/shared/data-states";
import { TabBar, type TabDef } from "@/components/shared/tabs";
import { useAuth } from "@/features/auth/hooks/use-auth";
import { defaultDateRange } from "../lib/date-range";
import type { DateRange } from "../api/types";
import { DateRangeControl } from "./date-range-control";
import { SummaryTab } from "./summary-tab";
import { CustomersTab } from "./customers-tab";
import { ByDimensionTab } from "./by-dimension-tab";
import { UnprofitableTab } from "./unprofitable-tab";
import { SettingsTab } from "./settings-tab";

const TABS: TabDef[] = [
  { value: "summary", label: "Summary" },
  { value: "customers", label: "Customers" },
  { value: "by-dimension", label: "By dimension" },
  { value: "unprofitable", label: "Unprofitable" },
  { value: "settings", label: "Settings" },
];

/** Tabs that share the analytical start/end date-range control. */
const RANGE_TABS = new Set(["summary", "customers", "by-dimension"]);

export function MarginPage() {
  const { isBillingMode, defaultCurrency } = useAuth();
  const [tab, setTab] = useState("summary");
  const [range, setRange] = useState<DateRange>(defaultDateRange);

  if (!isBillingMode) return <ProductUnavailable product="Margin" />;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Margin"
        description="Track unit economics — revenue against provider cost — across customers, dimensions, and periods."
      />

      <div className="flex flex-col gap-4">
        <TabBar tabs={TABS} value={tab} onChange={setTab} />
        {RANGE_TABS.has(tab) && (
          <DateRangeControl value={range} onChange={setRange} />
        )}
      </div>

      {tab === "summary" && (
        <SummaryTab range={range} currency={defaultCurrency} />
      )}
      {tab === "customers" && (
        <CustomersTab range={range} currency={defaultCurrency} />
      )}
      {tab === "by-dimension" && (
        <ByDimensionTab range={range} currency={defaultCurrency} />
      )}
      {tab === "unprofitable" && (
        <UnprofitableTab currency={defaultCurrency} />
      )}
      {tab === "settings" && <SettingsTab currency={defaultCurrency} />}
    </div>
  );
}
