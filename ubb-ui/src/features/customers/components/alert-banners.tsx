// src/features/customers/components/alert-banners.tsx
import { AlertCircle } from "lucide-react";
import { useAuthStore } from "@/stores/auth-store";
import type { CustomerMappingStats } from "../api/types";

interface AlertBannersProps {
  stats: CustomerMappingStats;
  onFilterUnmapped: () => void;
  onScrollToOrphans: () => void;
}

export function AlertBanners({
  stats,
  onFilterUnmapped,
  onScrollToOrphans,
}: AlertBannersProps) {
  const tenantMode = useAuthStore((s) => s.tenantMode);

  return (
    <div className="space-y-2">
      {stats.newCustomersSinceLastSync > 0 && (
        <div className="flex items-center gap-2.5 rounded-md border border-amber-border bg-amber-light px-3.5 py-2.5">
          <AlertCircle className="h-4 w-4 shrink-0 text-amber" />
          <div className="flex-1 text-[12px] leading-relaxed text-amber-text">
            <strong>
              {stats.newCustomersSinceLastSync} new Stripe customer
              {stats.newCustomersSinceLastSync !== 1 && "s"}
            </strong>{" "}
            were detected in the last sync and need to be mapped to an SDK
            identifier before their revenue and costs can be tracked.
          </div>
          <button
            type="button"
            className="shrink-0 rounded-full bg-accent-base px-3 py-1 text-[12px] font-medium text-text-inverse hover:bg-accent-hover"
            onClick={onFilterUnmapped}
          >
            Map them now
          </button>
        </div>
      )}

      {stats.orphanedEvents > 0 && (
        <div className="flex items-center gap-2.5 rounded-md border border-red-border bg-red-light px-3.5 py-2.5">
          <AlertCircle className="h-4 w-4 shrink-0 text-red" />
          <div className="flex-1 text-[12px] leading-relaxed text-red-text">
            <strong>{stats.orphanedEvents} events</strong> arrived with
            customer IDs that don&apos;t match any mapping.
            {tenantMode === "billing"
              ? " These events represent potential revenue leakage."
              : " These events are tracked but can\u2019t be attributed to a Stripe customer."}
          </div>
          <button
            type="button"
            className="shrink-0 rounded-full border border-red-border px-3 py-1 text-[12px] font-medium text-red-text hover:bg-red-light"
            onClick={onScrollToOrphans}
          >
            Review
          </button>
        </div>
      )}
    </div>
  );
}
