// src/features/reconciliation/components/distribution-mode-selector.tsx
import type { DistributionMode } from "../api/types";
import { cn } from "@/lib/utils";

interface DistributionModeOption {
  value: DistributionMode;
  label: string;
  sub: string;
}

const DIST_MODES: DistributionModeOption[] = [
  { value: "lump_sum", label: "Lump sum", sub: "Single date" },
  { value: "even_daily", label: "Even daily", sub: "Split equally" },
  { value: "proportional", label: "Proportional", sub: "Match existing" },
  { value: "manual", label: "Manual", sub: "Set each day" },
];

interface DistributionModeSelectorProps {
  value: DistributionMode;
  onChange: (mode: DistributionMode) => void;
}

export function DistributionModeSelector({ value, onChange }: DistributionModeSelectorProps) {
  return (
    <div>
      <div className="mb-2 text-muted font-medium">Distribution</div>
      <div className="grid grid-cols-4 gap-2">
        {DIST_MODES.map((m) => (
          <button
            key={m.value}
            type="button"
            onClick={() => onChange(m.value)}
            className={cn(
              "rounded-md border px-2.5 py-2 text-left transition-colors",
              value === m.value ? "border-2 border-foreground" : "border-border hover:bg-accent",
            )}
          >
            <div className="text-label font-medium">{m.label}</div>
            <div className="text-tiny text-muted-foreground">{m.sub}</div>
          </button>
        ))}
      </div>
    </div>
  );
}
