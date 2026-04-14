// src/features/billing/components/margin-stats.tsx
import { cn } from "@/lib/utils";
import type { MarginStats } from "../api/types";

interface MarginStatsProps {
  stats: MarginStats;
}

interface BillingStatProps {
  label: string;
  value: string;
  subtitle: string;
  tinted?: boolean;
}

function BillingStat({ label, value, subtitle, tinted }: BillingStatProps) {
  return (
    <div
      className={cn(
        "rounded-md border px-4 pt-3.5 pb-3",
        tinted
          ? "border-green-border bg-green-light"
          : "border-border bg-bg-surface",
      )}
    >
      <div
        className={cn(
          "text-[10px] font-bold uppercase tracking-[0.06em]",
          tinted ? "text-green" : "text-text-muted",
        )}
      >
        {label}
      </div>
      <div
        className={cn(
          "mt-1.5 text-[22px] font-bold leading-none tracking-[-0.5px]",
          tinted ? "text-green-text" : "text-text-primary",
        )}
      >
        {value}
      </div>
      <div
        className={cn(
          "mt-1.5 text-[11px]",
          tinted ? "text-green" : "text-text-muted",
        )}
      >
        {subtitle}
      </div>
    </div>
  );
}

export function MarginStatsGrid({ stats }: MarginStatsProps) {
  return (
    <div className="grid grid-cols-4 gap-2.5">
      <BillingStat
        label="Blended margin"
        value={`${stats.blendedMargin}%`}
        subtitle="Weighted by cost volume"
      />
      <BillingStat
        label="API costs (30d)"
        value={`$${stats.apiCosts30d.toLocaleString()}`}
        subtitle="Your expense"
      />
      <BillingStat
        label="Customer billings (30d)"
        value={`$${stats.customerBillings30d.toLocaleString()}`}
        subtitle="Debited from balances"
      />
      <BillingStat
        label="Margin earned (30d)"
        value={`$${stats.marginEarned30d.toLocaleString()}`}
        subtitle="Billings minus costs"
        tinted
      />
    </div>
  );
}
