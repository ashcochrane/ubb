import { useRef, useState } from "react";
import { Link } from "@tanstack/react-router";
import { PageHeader } from "@/components/shared/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuthStore } from "@/stores/auth-store";
import { useCustomerMapping } from "../api/queries";
import type { CustomerFilterKey } from "../api/types";
import { SyncStatusBar } from "./sync-status-bar";
import { MappingStatsGrid } from "./mapping-stats-grid";
import { AlertBanners } from "./alert-banners";
import { CustomerTable } from "./customer-table";
import { OrphanedEventsSection } from "./orphaned-events-section";

export function CustomerMappingPage() {
  const tenantMode = useAuthStore((s) => s.tenantMode);
  const { data, isLoading } = useCustomerMapping();
  const [activeFilter, setActiveFilter] = useState<CustomerFilterKey>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [editingCustomerId, setEditingCustomerId] = useState<string | null>(
    null,
  );
  const orphanRef = useRef<HTMLDivElement>(null);

  if (tenantMode === "track") {
    return (
      <div className="space-y-6">
        <PageHeader
          title="Customer mapping"
          description="Manage how your Stripe customers connect to the identifiers your SDK sends."
        />
        <div className="rounded-lg border border-dashed p-12 text-center">
          <h3 className="text-sm font-medium">Connect Stripe to manage customer mappings</h3>
          <p className="mt-1 text-xs text-muted-foreground">
            Customer mapping requires a Stripe connection to link your Stripe
            customers with SDK identifiers for accurate cost tracking and revenue attribution.
          </p>
          <Link
            to="/settings"
            className="mt-3 inline-block rounded-lg bg-primary px-4 py-2 text-xs text-primary-foreground hover:bg-primary/90"
          >
            Go to Settings
          </Link>
        </div>
      </div>
    );
  }

  if (isLoading || !data) {
    return (
      <div className="space-y-4">
        <PageHeader title="Customer mapping" />
        <Skeleton className="h-12 rounded-lg" />
        <div className="grid grid-cols-4 gap-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-[68px] rounded-lg" />
          ))}
        </div>
        <Skeleton className="h-10 rounded-lg" />
        <Skeleton className="h-64 rounded-xl" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Customer mapping"
        description="Manage how your Stripe customers connect to the identifiers your SDK sends. Every mapping must be correct for accurate cost tracking, revenue attribution, and billing."
      />

      <SyncStatusBar syncStatus={data.syncStatus} />

      <MappingStatsGrid stats={data.stats} />

      <AlertBanners
        stats={data.stats}
        onFilterUnmapped={() => setActiveFilter("unmapped")}
        onScrollToOrphans={() =>
          orphanRef.current?.scrollIntoView({ behavior: "smooth" })
        }
      />

      <CustomerTable
        customers={data.customers}
        activeFilter={activeFilter}
        onFilterChange={setActiveFilter}
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        editingCustomerId={editingCustomerId}
        onEditingChange={setEditingCustomerId}
      />

      <div ref={orphanRef}>
        <OrphanedEventsSection
          orphans={data.orphanedIdentifiers}
          customers={data.customers}
        />
      </div>
    </div>
  );
}
