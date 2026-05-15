// src/features/reconciliation/components/insert-period-panel.tsx
import { memo, useState } from "react";
import { Loader2 } from "lucide-react";
import type { PricingVersion } from "../api/types";
import { useReconciliationStore } from "../stores/reconciliation-store";

interface InsertPeriodPanelProps {
  version: PricingVersion;
  versions: PricingVersion[];
  onApply: (versionId: string, splitDate: string, splitTime: string, newPrices: Record<string, number>, reason: string) => Promise<void>;
}

function formatVersionLabel(v: PricingVersion): string {
  const start = new Date(v.startDate).toLocaleDateString("en-AU", { day: "numeric", month: "short" });
  const end = v.endDate
    ? new Date(v.endDate).toLocaleDateString("en-AU", { day: "numeric", month: "short" })
    : "now";
  return `${v.label} (${start} — ${end})`;
}

function InsertPeriodPanelImpl({ version, versions, onApply }: InsertPeriodPanelProps) {
  const closePanel = useReconciliationStore((s) => s.closePanel);
  const [selectedVersionId, setSelectedVersionId] = useState(version.id);
  const selectedVersion = versions.find((v) => v.id === selectedVersionId) ?? version;

  const [splitDate, setSplitDate] = useState("");
  const [splitTime, setSplitTime] = useState("00:00");
  const [prices, setPrices] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {};
    for (const d of version.dimensions) {
      init[d.key] = d.unitPrice.toString();
    }
    return init;
  });
  const [reason, setReason] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // When the selected version changes, reset prices to that version's dimensions
  const handleVersionChange = (id: string) => {
    setSelectedVersionId(id);
    const v = versions.find((ver) => ver.id === id);
    if (v) {
      const init: Record<string, string> = {};
      for (const d of v.dimensions) {
        init[d.key] = d.unitPrice.toString();
      }
      setPrices(init);
      setSplitDate("");
    }
  };

  const handleApply = async () => {
    if (!reason.trim() || !splitDate) return;
    setLoading(true);
    setError(null);
    try {
      const newPrices: Record<string, number> = {};
      for (const d of selectedVersion.dimensions) {
        newPrices[d.key] = parseFloat(prices[d.key] ?? "") || d.unitPrice;
      }
      await onApply(selectedVersionId, splitDate, splitTime, newPrices, reason);
      closePanel();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to insert period.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rounded-md border border-blue bg-blue-light px-4 py-4">
      <h3 className="text-[13px] font-semibold">Insert a pricing period</h3>
      <p className="mt-0.5 text-label text-muted-foreground">
        Split {selectedVersion.label} at a date to apply different prices for part of its period.
      </p>

      {/* Fix #5: Version selector dropdown */}
      <div className="mt-3">
        <label className="mb-1 block text-muted font-medium">Split version</label>
        <select
          value={selectedVersionId}
          onChange={(e) => handleVersionChange(e.target.value)}
          className="w-full rounded-md border border-border bg-bg-surface px-3 py-1.5 text-[12px] outline-none focus:border-muted-foreground"
        >
          {versions.map((v) => (
            <option key={v.id} value={v.id}>
              {formatVersionLabel(v)}
            </option>
          ))}
        </select>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3">
        <div>
          <label className="mb-1 block text-muted font-medium">Split at date</label>
          <input
            type="date"
            value={splitDate}
            onChange={(e) => setSplitDate(e.target.value)}
            min={selectedVersion.startDate}
            max={selectedVersion.endDate ?? undefined}
            className="w-full rounded-md border border-border bg-bg-surface px-3 py-1.5 text-[12px] outline-none focus:border-muted-foreground"
          />
        </div>
        <div>
          <label className="mb-1 block text-muted font-medium">Time</label>
          <input
            type="time"
            value={splitTime}
            onChange={(e) => setSplitTime(e.target.value)}
            className="w-full rounded-md border border-border bg-bg-surface px-3 py-1.5 text-[12px] outline-none focus:border-muted-foreground"
          />
        </div>
      </div>

      <div className="mt-3">
        <div className="mb-2 text-label font-medium">New period prices</div>
        <div className="space-y-2">
          {selectedVersion.dimensions.map((d) => (
            <div key={d.key} className="grid grid-cols-[110px_1fr_16px_1fr] items-center gap-2">
              <span className="font-mono text-label">{d.key}</span>
              <span className="text-right font-mono text-label text-muted-foreground">${d.unitPrice.toFixed(10)}</span>
              <span className="text-center text-label text-muted-foreground">→</span>
              <div className="relative">
                <span className="absolute left-2 top-1/2 -translate-y-1/2 text-label text-muted-foreground">$</span>
                <input
                  type="number"
                  step="any"
                  value={prices[d.key] ?? ""}
                  onChange={(e) => setPrices((p) => ({ ...p, [d.key]: e.target.value }))}
                  className="w-full rounded border border-accent-border bg-bg-surface py-1 pl-5 pr-2 font-mono text-label outline-none focus:border-muted-foreground"
                />
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-3">
        <label className="mb-1 block text-muted font-medium">Reason (required)</label>
        <textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="e.g. Google increased input token pricing effective 10 Feb."
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
          className="rounded-md border border-border px-3 py-1.5 text-label text-muted-foreground hover:bg-accent"
        >
          Preview events
        </button>
        <button
          type="button"
          onClick={handleApply}
          disabled={!reason.trim() || !splitDate || loading}
          className="rounded-md bg-blue px-3 py-1.5 text-label font-medium text-text-inverse hover:opacity-90 disabled:opacity-50"
        >
          {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : "Apply and recalculate"}
        </button>
      </div>
    </div>
  );
}

export const InsertPeriodPanel = memo(InsertPeriodPanelImpl);
