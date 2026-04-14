// src/features/billing/components/margin-edit-panel.tsx
import { useState } from "react";
import { Loader2 } from "lucide-react";
import type { MarginNode, MarginLevel } from "../api/types";
import { useUpdateMargin } from "../api/queries";
import { ImpactPreview } from "./impact-preview";
import { cn } from "@/lib/utils";

interface MarginEditPanelProps {
  node: MarginNode;
  onClose: () => void;
}

const levelDescriptions: Record<MarginLevel, string> = {
  default: "Applies to all products and cards without overrides.",
  product: "Changes apply to future API events billed through all cards within this product.",
  card: "Changes apply to future API events billed through this card only.",
};

export function MarginEditPanel({ node, onClose }: MarginEditPanelProps) {
  const [newPct, setNewPct] = useState(node.marginPct);
  const [inherit, setInherit] = useState(false);
  const [when, setWhen] = useState<"now" | "sched">("now");
  const [schedDate, setSchedDate] = useState("2026-04-01T00:00");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const updateMutation = useUpdateMargin();

  const canInherit = node.level !== "default" && node.source === "override";
  const inheritedPct = parseInt(node.parentSource.match(/(\d+)%/)?.[1] ?? "0", 10);
  const effectivePct = inherit ? inheritedPct : newPct;

  const handleApply = async () => {
    setError(null);
    try {
      await updateMutation.mutateAsync({
        nodeId: node.id,
        level: node.level,
        newMarginPct: effectivePct,
        inherit,
        effectiveness: when === "now" ? "immediately" : "scheduled",
        effectiveDate: when === "sched" ? schedDate : undefined,
        reason,
      });
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update margin.");
    }
  };

  return (
    <div className="rounded-md border-2 border-accent-border bg-bg-surface px-4 py-4">
      <div className="mb-1 text-[14px] font-semibold text-text-primary">
        Edit margin: {node.name}
      </div>
      <div className="mb-4 text-[11px] text-text-muted">
        {levelDescriptions[node.level]}
      </div>

      {/* Current margin card */}
      <div className="mb-4 rounded-md border-l-2 border-accent-base bg-bg-subtle px-3 py-2">
        <span className="text-[11px] text-text-muted">Current margin: </span>
        <span className="font-mono text-[13px] font-semibold text-text-primary">{node.marginPct}%</span>
        <span className="ml-2 text-[10px] text-text-muted">from {node.source === "set" ? "Set directly" : node.parentSource}</span>
      </div>

      {/* Slider */}
      <div className={cn("mb-4", inherit && "pointer-events-none opacity-30")}>
        <div className="mb-1 flex items-center justify-between">
          <label className="text-[11px] font-medium text-text-primary">New margin</label>
          <span className="min-w-[50px] text-right font-mono text-[16px] font-semibold text-text-primary">{newPct}%</span>
        </div>
        <input
          type="range"
          min={0}
          max={200}
          step={5}
          value={newPct}
          onChange={(e) => setNewPct(Number(e.target.value))}
          className="w-full accent-accent-base"
        />
      </div>

      {/* Inherit toggle */}
      {canInherit && (
        <label className="mb-4 flex cursor-pointer items-center gap-2.5">
          <div
            onClick={() => setInherit(!inherit)}
            className={cn(
              "flex h-4 w-4 items-center justify-center rounded-sm border-[1.5px] transition-colors",
              inherit ? "border-accent-base bg-accent-base" : "border-border-mid",
            )}
          >
            {inherit && <span className="text-[10px] text-text-inverse">&#10003;</span>}
          </div>
          <span className="text-[11px] text-text-muted">
            Revert to inherited value ({inheritedPct}%)
          </span>
        </label>
      )}

      {/* Impact preview */}
      <div className="mb-4">
        <ImpactPreview
          currentPct={node.marginPct}
          newPct={effectivePct}
          billings30d={node.billings30d}
        />
      </div>

      {/* When */}
      <div className="mb-4">
        <div className="mb-2 text-[12px] font-medium text-text-primary">When should this take effect?</div>
        <div className="flex gap-1.5">
          <button
            type="button"
            onClick={() => setWhen("now")}
            className={cn(
              "rounded-full border px-3.5 py-1.5 text-[11px] font-medium transition-colors",
              when === "now"
                ? "border-accent-base bg-accent-base text-text-inverse"
                : "border-border-mid bg-bg-surface text-text-secondary hover:bg-bg-subtle",
            )}
          >
            Immediately
          </button>
          <button
            type="button"
            onClick={() => setWhen("sched")}
            className={cn(
              "rounded-full border px-3.5 py-1.5 text-[11px] font-medium transition-colors",
              when === "sched"
                ? "border-accent-base bg-accent-base text-text-inverse"
                : "border-border-mid bg-bg-surface text-text-secondary hover:bg-bg-subtle",
            )}
          >
            Schedule for later
          </button>
        </div>
        {when === "sched" && (
          <div className="mt-2">
            <label className="mb-1 block text-[11px] font-medium text-text-primary">Effective date and time</label>
            <input
              type="datetime-local"
              value={schedDate}
              onChange={(e) => setSchedDate(e.target.value)}
              className="rounded-md border border-border-mid bg-bg-surface px-2.5 py-1.5 text-[12px] text-text-primary outline-none focus:border-accent-base"
            />
            <p className="mt-0.5 text-[10px] text-text-muted">
              Current margin applies until this time. New margin applies to all events after.
            </p>
          </div>
        )}
      </div>

      {/* Reason */}
      <div className="mb-4">
        <label className="mb-1 block text-[11px] font-medium text-text-primary">Reason for change</label>
        <textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="e.g. Increasing margin to reflect higher value-add..."
          className="min-h-[50px] w-full rounded-md border border-border-mid bg-bg-surface px-3 py-2 text-[12px] text-text-primary outline-none focus:border-accent-base"
        />
        <p className="mt-0.5 text-[10px] text-text-muted">
          Recorded in change history. Visible to your team.
        </p>
      </div>

      {error && <p className="mb-3 text-[11px] text-red">{error}</p>}

      {/* Actions */}
      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={onClose}
          className="rounded-full border border-border-mid px-4 py-1.5 text-[12px] font-medium text-text-secondary hover:bg-bg-subtle"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={handleApply}
          disabled={updateMutation.isPending || (effectivePct === node.marginPct && !inherit)}
          className="rounded-full bg-accent-base px-5 py-1.5 text-[12px] font-medium text-text-inverse hover:bg-accent-hover disabled:opacity-50"
        >
          {updateMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Apply margin change"}
        </button>
      </div>
    </div>
  );
}
