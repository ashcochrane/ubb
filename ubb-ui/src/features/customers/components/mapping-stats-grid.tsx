import { cn } from "@/lib/utils";
import type { CustomerMappingStats } from "../api/types";

interface MappingStatsGridProps {
  stats: CustomerMappingStats;
}

interface SemanticStatProps {
  label: string;
  value: React.ReactNode;
  subtitle: string;
  color?: "default" | "green" | "amber" | "red";
}

const colorMap = {
  default: {
    card: "border-border bg-bg-surface",
    label: "text-text-muted",
    value: "",
    sub: "text-text-muted",
  },
  green: {
    card: "border-green-border bg-green-light",
    label: "text-green",
    value: "text-green-text",
    sub: "text-green",
  },
  amber: {
    card: "border-amber-border bg-amber-light",
    label: "text-amber",
    value: "text-amber-text",
    sub: "text-amber",
  },
  red: {
    card: "border-red-border bg-red-light",
    label: "text-red",
    value: "text-red-text",
    sub: "text-red",
  },
};

function SemanticStat({ label, value, subtitle, color = "default" }: SemanticStatProps) {
  const c = colorMap[color];
  return (
    <div className={cn("rounded-md border px-4 pt-3.5 pb-3", c.card)}>
      <div className={cn("text-[10px] font-bold uppercase tracking-[0.06em]", c.label)}>
        {label}
      </div>
      <div className={cn("mt-1.5 text-[24px] font-bold leading-none tracking-[-0.5px]", c.value)}>
        {value}
      </div>
      <div className={cn("mt-1.5 text-[11px]", c.sub)}>{subtitle}</div>
    </div>
  );
}

export function MappingStatsGrid({ stats }: MappingStatsGridProps) {
  return (
    <div className="grid grid-cols-4 gap-2.5">
      <SemanticStat
        label="Stripe customers"
        value={stats.totalCustomers}
        subtitle={`${stats.newCustomersSinceLastSync} added since last month`}
      />
      <SemanticStat
        label="Mapped"
        value={stats.mapped}
        subtitle="Fully connected"
        color="green"
      />
      <SemanticStat
        label="Unmapped"
        value={stats.unmapped}
        subtitle="Need attention"
        color="amber"
      />
      <SemanticStat
        label="Orphaned events"
        value={stats.orphanedEvents}
        subtitle={`${stats.orphanedIdentifiers} unknown SDK IDs`}
        color="red"
      />
    </div>
  );
}
