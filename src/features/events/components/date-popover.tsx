import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

type DatePreset = "7d" | "30d" | "90d" | "all";

interface DatePopoverProps {
  dateFrom: string;
  dateTo: string;
  activePreset: DatePreset | null;
  onApply: (from: string, to: string, preset: DatePreset | null) => void;
  onClose: () => void;
  anchorRect: DOMRect | null;
}

const PRESETS: DatePreset[] = ["7d", "30d", "90d", "all"];

export function DatePopover({
  dateFrom,
  dateTo,
  activePreset,
  onApply,
  onClose,
  anchorRect,
}: DatePopoverProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [from, setFrom] = useState(dateFrom);
  const [to, setTo] = useState(dateTo);
  const [preset, setPreset] = useState<DatePreset | null>(activePreset);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        onClose();
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [onClose]);

  function handlePreset(p: DatePreset) {
    setPreset(p);
    const toDate = new Date();
    const toStr = toDate.toISOString().split("T")[0]!;
    setTo(toStr);
    if (p === "all") {
      setFrom("2026-01-01");
    } else {
      const days = p === "7d" ? 7 : p === "30d" ? 30 : 90;
      const fromDate = new Date(toDate);
      fromDate.setDate(fromDate.getDate() - days);
      setFrom(fromDate.toISOString().split("T")[0]!);
    }
  }

  if (!anchorRect) return null;

  return (
    <div
      ref={ref}
      className="absolute z-50 min-w-[260px] rounded-md border border-border bg-bg-surface p-3 shadow-lg"
      style={{ left: anchorRect.left, top: anchorRect.bottom + 4 }}
    >
      <div className="mb-2.5 flex gap-1">
        {PRESETS.map((p) => (
          <button
            key={p}
            className={cn(
              "rounded-full px-3 py-1 text-[11px] font-medium transition-colors",
              preset === p
                ? "bg-accent-base text-text-inverse"
                : "border border-border-mid text-text-secondary hover:bg-bg-subtle",
            )}
            onClick={() => handlePreset(p)}
          >
            {p === "all" ? "All" : p}
          </button>
        ))}
      </div>
      <div className="mb-1.5 flex items-center gap-2">
        <label className="min-w-[32px] text-[11px] text-text-muted">From</label>
        <input
          type="date"
          value={from}
          onChange={(e) => { setFrom(e.target.value); setPreset(null); }}
          className="flex-1 rounded-sm border border-border-mid bg-bg-surface px-2.5 py-[5px] font-mono text-[11px] text-text-primary outline-none focus:border-accent-dark focus:ring-2 focus:ring-accent-base/15"
        />
      </div>
      <div className="flex items-center gap-2">
        <label className="min-w-[32px] text-[11px] text-text-muted">To</label>
        <input
          type="date"
          value={to}
          onChange={(e) => { setTo(e.target.value); setPreset(null); }}
          className="flex-1 rounded-sm border border-border-mid bg-bg-surface px-2.5 py-[5px] font-mono text-[11px] text-text-primary outline-none focus:border-accent-dark focus:ring-2 focus:ring-accent-base/15"
        />
      </div>
      <div className="mt-2.5 flex justify-between border-t border-border pt-2">
        <button className="text-[11px] text-text-secondary hover:text-text-primary" onClick={onClose}>
          Cancel
        </button>
        <button
          className="text-[11px] font-medium text-accent-text hover:text-accent-dark"
          onClick={() => onApply(from, to, preset)}
        >
          Apply
        </button>
      </div>
    </div>
  );
}
