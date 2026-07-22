// src/features/reconciliation/components/edit-prices-panel.tsx
import { memo, useState } from "react";
import { Loader2 } from "lucide-react";
import type { PricingVersion } from "../api/types";
import { useReconciliationStore } from "../stores/reconciliation-store";

interface EditPricesPanelProps {
  version: PricingVersion;
  onApply: (newPrices: Record<string, number>, reason: string) => Promise<void>;
}

function EditPricesPanelImpl({ version, onApply }: EditPricesPanelProps) {
  const closePanel = useReconciliationStore((s) => s.closePanel);
  const [prices, setPrices] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {};
    for (const d of version.dimensions) {
      init[d.key] = "";
    }
    return init;
  });
  const [reason, setReason] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleApply = async () => {
    if (!reason.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const newPrices: Record<string, number> = {};
      for (const d of version.dimensions) {
        const val = prices[d.key];
        newPrices[d.key] = val ? parseFloat(val) : d.unitPrice;
      }
      await onApply(newPrices, reason);
      closePanel();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to apply correction.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rounded-md border border-accent-border bg-accent-ghost px-4 py-4">
      <h3 className="text-[13px] font-semibold">Edit prices for {version.label}</h3>
      <p className="mt-0.5 text-label text-muted-foreground">
        All events in this period will be recalculated at the corrected prices.
      </p>

      <div className="mt-3 space-y-2">
        {version.dimensions.map((d) => (
          <div key={d.key} className="grid grid-cols-[110px_1fr_16px_1fr] items-center gap-2">
            <span className="font-mono text-label">{d.key}</span>
            <span className="text-right font-mono text-label text-muted-foreground">${d.unitPrice.toFixed(10)}</span>
            <span className="text-center text-label text-muted-foreground">→</span>
            <div className="relative">
              <span className="absolute left-2 top-1/2 -translate-y-1/2 text-label text-muted-foreground">$</span>
              <input
                type="number"
                step="any"
                value={prices[d.key]}
                onChange={(e) => setPrices((p) => ({ ...p, [d.key]: e.target.value }))}
                placeholder={d.unitPrice.toFixed(10)}
                className="w-full rounded border border-border bg-bg-surface py-1 pl-5 pr-2 font-mono text-label outline-none focus:border-muted-foreground"
              />
            </div>
          </div>
        ))}
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
          disabled={!reason.trim() || loading}
          className="rounded-md bg-accent-base px-3 py-1.5 text-label font-medium text-text-inverse hover:opacity-90 disabled:opacity-50"
        >
          {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : "Apply correction"}
        </button>
      </div>
    </div>
  );
}

export const EditPricesPanel = memo(EditPricesPanelImpl);
