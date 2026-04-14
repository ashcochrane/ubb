// src/features/reconciliation/components/adjust-boundary-panel.tsx
import { memo, useState } from "react";
import { Loader2 } from "lucide-react";
import type { PricingVersion } from "../api/types";
import { useReconciliationStore } from "../stores/reconciliation-store";

interface AdjustBoundaryPanelProps {
  version: PricingVersion;
  nextVersion?: PricingVersion;
  onApply: (newDate: string, newTime: string, reason: string) => Promise<void>;
}

function AdjustBoundaryPanelImpl({ version, nextVersion, onApply }: AdjustBoundaryPanelProps) {
  const closePanel = useReconciliationStore((s) => s.closePanel);
  const [date, setDate] = useState(version.endDate ?? "");
  const [time, setTime] = useState("00:00");
  const [reason, setReason] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const originalDate = version.endDate ?? "";
  const hasChanged = date !== originalDate || time !== "00:00";

  const handleApply = async () => {
    if (!reason.trim() || !date) return;
    setLoading(true);
    setError(null);
    try {
      await onApply(date, time, reason);
      closePanel();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to adjust boundary.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rounded-md border border-border bg-bg-surface px-4 py-4">
      <h3 className="text-[13px] font-semibold">Adjust version boundary</h3>
      <p className="mt-0.5 text-label text-muted-foreground">
        Move the boundary between two adjacent versions. Events crossing the new boundary will be repriced.
      </p>

      {/* Before/after visual */}
      <div className="mt-3 grid grid-cols-[1fr_auto_1fr] items-center gap-3">
        <div className="rounded-md bg-bg-subtle px-3 py-2 text-center">
          <div className="text-label font-medium">{version.label}</div>
          <div className="text-muted text-muted-foreground">ends</div>
        </div>
        <div className="h-8 w-px bg-border" />
        <div className="rounded-md bg-bg-subtle px-3 py-2 text-center">
          <div className="text-label font-medium">{nextVersion?.label ?? "—"}</div>
          <div className="text-muted text-muted-foreground">starts</div>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3">
        <div>
          <label className="mb-1 block text-muted font-medium">Move boundary to</label>
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="w-full rounded-md border border-border bg-bg-surface px-3 py-1.5 text-[12px] outline-none focus:border-muted-foreground"
          />
        </div>
        <div>
          <label className="mb-1 block text-muted font-medium">Time (optional)</label>
          <input
            type="time"
            value={time}
            onChange={(e) => setTime(e.target.value)}
            className="w-full rounded-md border border-border bg-bg-surface px-3 py-1.5 text-[12px] outline-none focus:border-muted-foreground"
          />
        </div>
      </div>

      {/* Fix #10: Change status indicator */}
      <p className="mt-2 text-label text-muted-foreground/60">
        {hasChanged ? `Boundary moves from ${originalDate} → ${date} at ${time}` : "No change yet"}
      </p>

      <div className="mt-3">
        <label className="mb-1 block text-muted font-medium">Reason (required)</label>
        <textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="e.g. Corrected to actual pricing effective date."
          className="min-h-[48px] w-full rounded-md border border-border bg-bg-surface px-3 py-2 text-label outline-none focus:border-muted-foreground"
        />
      </div>

      {error && <p className="mt-2 text-label text-red">{error}</p>}

      <div className="mt-3 flex justify-end gap-2">
        <button type="button" onClick={closePanel} className="rounded-md border border-border px-3 py-1.5 text-label text-muted-foreground hover:bg-accent">
          Cancel
        </button>
        <button
          type="button"
          onClick={handleApply}
          disabled={!reason.trim() || !date || loading}
          className="rounded-md bg-foreground px-3 py-1.5 text-label font-medium text-background hover:opacity-90 disabled:opacity-50"
        >
          {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : "Apply boundary change"}
        </button>
      </div>
    </div>
  );
}

export const AdjustBoundaryPanel = memo(AdjustBoundaryPanelImpl);
