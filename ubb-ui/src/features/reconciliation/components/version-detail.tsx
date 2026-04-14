// src/features/reconciliation/components/version-detail.tsx
import type { PricingVersion } from "../api/types";
import { useReconciliationStore } from "../stores/reconciliation-store";
import { cn } from "@/lib/utils";

interface VersionDetailProps {
  version: PricingVersion;
}

const statusColors: Record<string, string> = {
  active: "bg-green-light text-green-text",
  superseded: "bg-muted text-muted-foreground",
  retroactive: "bg-blue-light text-blue-text",
};

/** Converts raw version labels to display format: "v1" → "Version 1", "v2b" → "Version 2b" */
function formatVersionLabel(label: string): string {
  const match = label.match(/^v(\d+)(.*)$/);
  if (!match) return label;
  return `Version ${match[1]}${match[2]}`;
}

export function VersionDetail({ version }: VersionDetailProps) {
  const openPanelFor = useReconciliationStore((s) => s.openPanelFor);

  const endLabel = version.endDate
    ? new Date(version.endDate).toLocaleDateString("en-GB", { day: "numeric", month: "short" })
    : "Today";
  const startLabel = new Date(version.startDate).toLocaleDateString("en-GB", { day: "numeric", month: "short" });

  return (
    <div className="rounded-md border border-border bg-bg-surface px-4 py-3.5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-[14px] font-semibold">{formatVersionLabel(version.label)}</span>
          <span className={cn("rounded-full px-2 py-0.5 text-muted font-medium", statusColors[version.status])}>
            {version.status}
          </span>
        </div>
      </div>

      <div className="mt-1 text-label text-muted-foreground">
        {startLabel} — {endLabel} ({version.durationDays} days)
      </div>

      <div className="mt-1 flex gap-4 text-label">
        <span>Events: <span className="font-mono font-medium">{version.eventCount.toLocaleString()}</span></span>
        <span>Cost: <span className="font-mono font-medium">${version.cost.toLocaleString()}</span></span>
      </div>

      {/* Dimension pricing table */}
      <div className="mt-3 rounded-md border border-border">
        <table className="w-full text-label">
          <thead>
            <tr className="border-b border-border bg-bg-subtle">
              <th className="px-3 py-1.5 text-left font-medium text-muted-foreground">Dimension</th>
              <th className="px-3 py-1.5 text-left font-medium text-muted-foreground">Type</th>
              <th className="px-3 py-1.5 text-right font-medium text-muted-foreground">Unit price</th>
              <th className="px-3 py-1.5 text-right font-medium text-muted-foreground">Display</th>
            </tr>
          </thead>
          <tbody>
            {version.dimensions.map((d) => (
              <tr key={d.key} className="border-b border-border/50 last:border-0">
                <td className="px-3 py-1.5 font-mono">{d.key}</td>
                <td className="px-3 py-1.5">
                  <span className="rounded-full bg-muted px-2 py-0.5 text-muted">{d.type === "per_unit" ? "per unit" : "flat"}</span>
                </td>
                <td className="px-3 py-1.5 text-right font-mono">${d.unitPrice.toFixed(10)}</td>
                <td className="px-3 py-1.5 text-right font-mono">{d.displayPrice}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Action buttons — vary by version status */}
      <div className="mt-3 flex gap-2">
        {version.status === "superseded" && (
          <button
            type="button"
            onClick={() => openPanelFor("edit-prices")}
            className="rounded-md bg-amber-light px-3 py-1.5 text-label font-medium text-amber-text hover:opacity-90"
          >
            Edit prices
          </button>
        )}
        {version.status === "retroactive" && (
          <button
            type="button"
            onClick={() => openPanelFor("edit-prices")}
            className="rounded-md bg-amber-light px-3 py-1.5 text-label font-medium text-amber-text hover:opacity-90"
          >
            Edit prices
          </button>
        )}
        <button
          type="button"
          onClick={() => openPanelFor("adjust-boundary")}
          className="rounded-md border border-border px-3 py-1.5 text-label text-muted-foreground hover:bg-accent"
        >
          Adjust boundaries
        </button>
        {version.status === "superseded" && (
          <button
            type="button"
            onClick={() => openPanelFor("insert-period")}
            className="rounded-md bg-blue-light px-3 py-1.5 text-label font-medium text-blue-text hover:opacity-90"
          >
            Split this period
          </button>
        )}
      </div>
    </div>
  );
}
