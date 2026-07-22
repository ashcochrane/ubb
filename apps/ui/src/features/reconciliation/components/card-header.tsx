// src/features/reconciliation/components/card-header.tsx
import { ArrowLeft } from "lucide-react";
import { Link } from "@tanstack/react-router";
import type { ReconciliationData } from "../api/types";
import { cn } from "@/lib/utils";

interface CardHeaderProps {
  data: ReconciliationData;
}

export function CardHeader({ data }: CardHeaderProps) {
  const { card, stats } = data;

  return (
    <div className="space-y-4">
      <Link
        to="/pricing-cards"
        className="inline-flex items-center gap-1 text-[12px] text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-3 w-3" /> Back to all cards
      </Link>

      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-[22px] font-bold">{card.name}</h1>
          <div className="text-[13px] text-muted-foreground">
            {card.provider}{" "}
            <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-label">{card.cardId}</code>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={cn(
              "rounded-full px-2.5 py-0.5 text-muted font-semibold",
              card.status === "active"
                ? "bg-green-light text-green-text"
                : "bg-muted text-muted-foreground",
            )}
          >
            {card.status === "active" ? "Active" : "Inactive"}
          </span>
          <button
            type="button"
            className="rounded-md border border-border px-3 py-1 text-label font-medium text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            Edit card
          </button>
        </div>
      </div>

      <div className="grid grid-cols-4 gap-2.5">
        <StatCard
          label="Originally tracked"
          value={`$${Math.round(stats.originalTracked).toLocaleString()}`}
          sub="Raw event costs"
        />
        <StatCard
          label="Reconciled total"
          value={`$${Math.round(stats.reconciledTotal).toLocaleString()}`}
          sub="After adjustments"
        />
        <StatCard
          label="Net adjustments"
          value={`${stats.netAdjustments >= 0 ? "+" : ""}$${Math.round(stats.netAdjustments)}`}
          sub={`${stats.adjustmentCount} adjustments applied`}
          valueColor={stats.netAdjustments > 0 ? "text-red-text" : "text-green-text"}
        />
        <StatCard
          label="Events / versions"
          value={`${(stats.eventCount / 1000).toFixed(0)}k / ${stats.currentVersion}`}
          sub={`Since ${stats.since}`}
        />
      </div>
    </div>
  );
}

function StatCard({ label, value, sub, valueColor }: {
  label: string;
  value: string;
  sub: string;
  valueColor?: string;
}) {
  return (
    <div className="rounded-md border border-border bg-bg-surface px-3 py-2.5">
      <div className="text-label text-muted-foreground">{label}</div>
      <div className={cn("mt-1 text-[17px] font-semibold", valueColor)}>{value}</div>
      <div className="mt-0.5 text-muted text-muted-foreground">{sub}</div>
    </div>
  );
}
