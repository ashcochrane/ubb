import { useState, useMemo, useCallback } from "react";
import { Loader2 } from "lucide-react";
import type { AdjustmentType, DistributionMode } from "../api/types";
import { useReconciliationStore } from "../stores/reconciliation-store";
import { DistributionPreview } from "./distribution-preview";
import { DistributionModeSelector } from "./distribution-mode-selector";
import { AllocationDisplay } from "./allocation-display";
import { getDayLabels, buildEvenAllocations } from "./day-labels";
import { cn } from "@/lib/utils";

interface AdjustmentsSectionProps {
  onRecord: (data: {
    type: AdjustmentType;
    amount: number;
    product: string | null;
    distributionMode: DistributionMode;
    distributionConfig: Record<string, unknown>;
    reason: string;
    evidence: string | null;
  }) => Promise<void>;
}

const ADJ_TYPES = [
  { value: "credit_refund" as const, label: "Credit or refund", sub: "Provider refund, billing credit, or cost reversal.", defaultAmt: -25 },
  { value: "missing_costs" as const, label: "Missing costs", sub: "Costs that were never tracked by the system.", defaultAmt: 45 },
];

export function AdjustmentsSection({ onRecord }: AdjustmentsSectionProps) {
  const openPanel = useReconciliationStore((s) => s.openPanel);
  const openPanelFor = useReconciliationStore((s) => s.openPanelFor);
  const closePanel = useReconciliationStore((s) => s.closePanel);
  const isOpen = openPanel === "adjustments";

  const [adjType, setAdjType] = useState<AdjustmentType>("credit_refund");
  const [amount, setAmount] = useState(-25);
  const [product, setProduct] = useState<string | null>(null);
  const [distMode, setDistMode] = useState<DistributionMode>("lump_sum");
  const [lumpDate, setLumpDate] = useState("2026-03-10");
  const [lumpTime, setLumpTime] = useState("00:00");
  const [periodStart, setPeriodStart] = useState("2026-03-01");
  const [periodEnd, setPeriodEnd] = useState("2026-03-07");
  const [proportionalBasis, setProportionalBasis] = useState<"card" | "product">("card");
  const [manualAllocations, setManualAllocations] = useState<Record<string, number>>({});
  const [reason, setReason] = useState("");
  const [evidence, setEvidence] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const manualDayLabels = useMemo(() => getDayLabels(periodStart, periodEnd), [periodStart, periodEnd]);

  const initManual = useCallback((start: string, end: string) => {
    setManualAllocations(buildEvenAllocations(start, end, amount));
  }, [amount]);

  const handleDistModeChange = (mode: DistributionMode) => {
    setDistMode(mode);
    if (mode === "manual") initManual(periodStart, periodEnd);
  };

  const handlePeriodStartChange = (value: string) => {
    setPeriodStart(value);
    if (distMode === "manual") initManual(value, periodEnd);
  };

  const handlePeriodEndChange = (value: string) => {
    setPeriodEnd(value);
    if (distMode === "manual") initManual(periodStart, value);
  };

  const handleManualAllocationChange = (label: string, value: number) => {
    setManualAllocations((prev) => ({ ...prev, [label]: value }));
  };

  const handleRecord = async () => {
    if (!reason.trim()) return;
    setLoading(true);
    setError(null);
    try {
      await onRecord({
        type: adjType, amount, product, distributionMode: distMode,
        distributionConfig: {
          lumpDate, lumpTime, periodStart, periodEnd,
          ...(distMode === "proportional" ? { proportionalBasis } : {}),
          ...(distMode === "manual" ? { manualAllocations } : {}),
        },
        reason, evidence: evidence || null,
      });
      closePanel();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to record adjustment.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between">
        <h2 className="text-[14px] font-semibold">Adjustments</h2>
        {!isOpen && (
          <button type="button" onClick={() => openPanelFor("adjustments")} className="rounded-md border border-border px-3 py-1.5 text-label text-muted-foreground hover:bg-accent">
            Record an adjustment
          </button>
        )}
      </div>
      <p className="mt-0.5 text-label text-muted-foreground">
        For costs outside the event pipeline — refunds, credits, missed data, or invoice reconciliation.
      </p>

      {isOpen && (
        <div className="mt-3 space-y-4 rounded-md border border-border bg-bg-surface px-4 py-4">
          {/* Type selector */}
          <div className="grid grid-cols-2 gap-2.5">
            {ADJ_TYPES.map((t) => (
              <button key={t.value} type="button" onClick={() => { setAdjType(t.value); setAmount(t.defaultAmt); }}
                className={cn("rounded-md border px-3 py-2.5 text-left transition-colors", adjType === t.value ? "border-2 border-foreground" : "border-border hover:bg-accent")}>
                <div className="text-[12px] font-medium">{t.label}</div>
                <div className="text-muted text-muted-foreground">{t.sub}</div>
              </button>
            ))}
          </div>

          {/* Amount + product */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-muted font-medium">Total amount ($)</label>
              <input type="number" step="any" value={amount} onChange={(e) => setAmount(parseFloat(e.target.value) || 0)}
                className="w-full rounded-md border border-border bg-bg-surface px-3 py-1.5 font-mono text-[12px] outline-none focus:border-muted-foreground" />
              <p className="mt-0.5 text-muted text-muted-foreground">Negative = credit/refund</p>
            </div>
            <div>
              <label className="mb-1 block text-muted font-medium">Attribute to product</label>
              <select value={product ?? ""} onChange={(e) => setProduct(e.target.value || null)}
                className="w-full rounded-md border border-border bg-bg-surface px-3 py-1.5 text-[12px] outline-none focus:border-muted-foreground">
                <option value="">No product (card-level)</option>
                <option value="property_search">Property search</option>
                <option value="doc_summariser">Doc summariser</option>
                <option value="content_gen">Content gen</option>
              </select>
            </div>
          </div>

          <DistributionModeSelector value={distMode} onChange={handleDistModeChange} />

          <AllocationDisplay
            mode={distMode} amount={amount}
            lumpDate={lumpDate} lumpTime={lumpTime}
            onLumpDateChange={setLumpDate} onLumpTimeChange={setLumpTime}
            periodStart={periodStart} periodEnd={periodEnd}
            onPeriodStartChange={handlePeriodStartChange} onPeriodEndChange={handlePeriodEndChange}
            proportionalBasis={proportionalBasis} onProportionalBasisChange={setProportionalBasis}
            manualDayLabels={manualDayLabels} manualAllocations={manualAllocations}
            onManualAllocationChange={handleManualAllocationChange}
          />

          <DistributionPreview
            mode={distMode} amount={amount}
            startDate={distMode === "lump_sum" ? lumpDate : periodStart}
            endDate={distMode === "lump_sum" ? lumpDate : periodEnd}
            manualAllocations={distMode === "manual" ? manualAllocations : undefined}
          />

          {/* Reason + evidence */}
          <div>
            <label className="mb-1 block text-muted font-medium">Reason (required)</label>
            <textarea value={reason} onChange={(e) => setReason(e.target.value)} placeholder="e.g. Google Cloud issued a $25 credit for service disruption on 10 Mar."
              className="min-h-[48px] w-full rounded-md border border-border bg-bg-surface px-3 py-2 text-label outline-none focus:border-muted-foreground" />
          </div>
          <div>
            <label className="mb-1 block text-muted font-medium">Supporting evidence (optional)</label>
            <input value={evidence} onChange={(e) => setEvidence(e.target.value)} placeholder="e.g. Invoice link, support ticket URL"
              className="w-full rounded-md border border-border bg-bg-surface px-3 py-1.5 text-label outline-none focus:border-muted-foreground" />
          </div>

          {error && <p className="text-label text-red">{error}</p>}

          <div className="flex justify-end gap-2">
            <button type="button" onClick={closePanel} className="rounded-md border border-border px-3 py-1.5 text-label text-muted-foreground hover:bg-accent">Cancel</button>
            <button type="button" onClick={handleRecord} disabled={!reason.trim() || loading}
              className="rounded-md bg-purple-fg px-3 py-1.5 text-label font-medium text-text-inverse hover:opacity-90 disabled:opacity-50">
              {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : "Record adjustment"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
