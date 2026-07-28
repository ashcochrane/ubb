import { Link } from "@tanstack/react-router";
import { ArrowLeft, UserRoundX } from "lucide-react";

import { isNotFound } from "@/api/problem";
import { CopyButton } from "@/components/shared/copy-button";
import { DateRangePicker } from "@/components/shared/date-range-picker";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorCard } from "@/components/shared/error-card";
import { ProductGate } from "@/components/shared/product-gate";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { resolveRange, type DateRange } from "@/lib/date-range";
import { cn } from "@/lib/utils";

import { useCustomerMargin } from "../api/queries";
import { BillingTab } from "./billing-tab";
import { OverviewTab } from "./overview-tab";
import { PricingTab } from "./pricing-tab";
import { SubscriptionTab } from "./subscription-tab";
import { UsageTab } from "./usage-tab";

const TABS = [
  { value: "overview", label: "Overview" },
  { value: "usage", label: "Usage" },
  { value: "billing", label: "Billing" },
  { value: "pricing", label: "Pricing" },
  { value: "subscription", label: "Subscription" },
] as const;

export type CustomerTab = (typeof TABS)[number]["value"];

export interface CustomerDetailSearch extends DateRange {
  tab?: CustomerTab;
}

export function CustomerDetailPage({
  customerId,
  search,
  onSearchChange,
}: {
  customerId: string;
  search: CustomerDetailSearch;
  onSearchChange: (next: CustomerDetailSearch) => void;
}) {
  const range = resolveRange(search);
  const margin = useCustomerMargin(customerId, range);
  // Unknown/stale ?tab= values fall back to Overview instead of rendering an
  // empty tab panel (the route schema also coerces them to undefined).
  const requestedTab = search.tab;
  const tab =
    requestedTab !== undefined && TABS.some((entry) => entry.value === requestedTab)
      ? requestedTab
      : "overview";

  if (margin.isLoading) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-9 w-72" />
        <Skeleton className="h-8 w-96" />
        <Skeleton className="h-64 w-full" />
      </div>
    );
  }

  if (margin.isError) {
    if (isNotFound(margin.error)) {
      return (
        <EmptyState
          icon={UserRoundX}
          title="Customer not found"
          description="This customer doesn't exist (or belongs to another workspace)."
        />
      );
    }
    return <ErrorCard error={margin.error} onRetry={() => void margin.refetch()} />;
  }

  const detail = margin.data;
  if (!detail) return null;

  return (
    // keepPreviousData keeps the page mounted across range changes; the
    // placeholder refresh dims subtly instead of blanking to skeletons.
    <div
      className={cn(
        "space-y-4 transition-opacity",
        margin.isPlaceholderData && "opacity-60",
      )}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <Link
            to="/customers"
            className="mb-1 inline-flex items-center gap-1 text-[12px] text-text-secondary hover:text-text-primary"
          >
            <ArrowLeft className="h-3.5 w-3.5" /> Customers
          </Link>
          <h1 className="truncate text-xl font-semibold tracking-tight">
            {detail.external_id}
          </h1>
          <div className="mt-1 flex items-center gap-1.5">
            <span className="font-mono text-[12px] text-text-secondary" title={customerId}>
              {customerId}
            </span>
            <CopyButton value={customerId} label="Copy customer ID" />
          </div>
        </div>
        <DateRangePicker
          value={{ start_date: search.start_date, end_date: search.end_date }}
          onChange={(next) => onSearchChange({ ...next, tab: search.tab })}
        />
      </div>

      <Tabs
        value={tab}
        onValueChange={(value) => {
          const entry = TABS.find((candidate) => candidate.value === value);
          onSearchChange({
            ...search,
            tab: entry && entry.value !== "overview" ? entry.value : undefined,
          });
        }}
      >
        <TabsList>
          {TABS.map((entry) => (
            <TabsTrigger key={entry.value} value={entry.value}>
              {entry.label}
            </TabsTrigger>
          ))}
        </TabsList>
        <TabsContent value="overview" className="pt-3">
          <OverviewTab customerId={customerId} margin={detail} range={range} />
        </TabsContent>
        <TabsContent value="usage" className="pt-3">
          <UsageTab customerId={customerId} range={range} />
        </TabsContent>
        <TabsContent value="billing" className="pt-3">
          <ProductGate product="billing">
            <BillingTab customerId={customerId} externalId={detail.external_id} />
          </ProductGate>
        </TabsContent>
        <TabsContent value="pricing" className="pt-3">
          <PricingTab customerId={customerId} />
        </TabsContent>
        <TabsContent value="subscription" className="pt-3">
          <ProductGate product="billing">
            <SubscriptionTab
              customerId={customerId}
              externalId={detail.external_id}
            />
          </ProductGate>
        </TabsContent>
      </Tabs>
    </div>
  );
}
