// src/features/billing/components/impact-preview.tsx
import { cn } from "@/lib/utils";

interface ImpactPreviewProps {
  currentPct: number;
  newPct: number;
  billings30d: number;
}

export function ImpactPreview({ currentPct, newPct, billings30d }: ImpactPreviewProps) {
  const cost30 = Math.round(billings30d / (1 + currentPct / 100));
  const oldBill = billings30d;
  const newBill = Math.round(cost30 * (1 + newPct / 100));
  const delta = newBill - oldBill;

  const deltaSign = delta >= 0 ? "+" : "-";
  const deltaDisplay = `${deltaSign}$${Math.abs(delta).toLocaleString()}`;

  const note = delta === 0
    ? "No change from current margin."
    : delta > 0
      ? `Customers would be billed $${Math.abs(delta).toLocaleString()}/mo more based on recent volume.`
      : `Customers would be billed $${Math.abs(delta).toLocaleString()}/mo less based on recent volume.`;

  return (
    <div className="rounded-md border border-border px-3.5 py-3">
      <div className="mb-2 text-[12px] font-medium text-text-primary">Impact estimate</div>
      <p className="mb-3 text-[11px] text-text-muted">
        Based on the last 30 days of billing volume. Actual results depend on future usage.
      </p>

      <div className="mb-2 grid items-center gap-0" style={{ gridTemplateColumns: "1fr 32px 1fr 32px 1fr" }}>
        <div className="rounded-md bg-bg-subtle px-2.5 py-2 text-center">
          <div className="text-[10px] text-text-muted">Was billing (30d)</div>
          <div className="font-mono text-[15px] font-medium text-text-muted line-through">
            ${oldBill.toLocaleString()}
          </div>
        </div>
        <div className="text-center text-[14px] text-text-muted">&rarr;</div>
        <div className="rounded-md bg-bg-subtle px-2.5 py-2 text-center">
          <div className="text-[10px] text-text-muted">Would be billing</div>
          <div className="font-mono text-[15px] font-medium text-text-primary">
            ${newBill.toLocaleString()}
          </div>
        </div>
        <div className="text-center text-[14px] text-text-muted">=</div>
        <div className="rounded-md bg-bg-subtle px-2.5 py-2 text-center">
          <div className="text-[10px] text-text-muted">Difference</div>
          <div className={cn(
            "font-mono text-[15px] font-medium",
            delta > 0 && "text-red-text",
            delta < 0 && "text-green-text",
          )}>
            {deltaDisplay}
          </div>
        </div>
      </div>

      <p className="text-center text-[10px] text-text-muted">{note}</p>
    </div>
  );
}
