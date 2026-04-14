// src/features/reconciliation/components/allocation-display.tsx
import type { DistributionMode } from "../api/types";
import { DateRangeFields } from "./date-range-fields";
import { ManualAllocation } from "./manual-allocation";

interface AllocationDisplayProps {
  mode: DistributionMode;
  amount: number;

  // Lump sum
  lumpDate: string;
  lumpTime: string;
  onLumpDateChange: (value: string) => void;
  onLumpTimeChange: (value: string) => void;

  // Ranged modes (even_daily, proportional, manual)
  periodStart: string;
  periodEnd: string;
  onPeriodStartChange: (value: string) => void;
  onPeriodEndChange: (value: string) => void;

  // Proportional
  proportionalBasis: "card" | "product";
  onProportionalBasisChange: (value: "card" | "product") => void;

  // Manual
  manualDayLabels: string[];
  manualAllocations: Record<string, number>;
  onManualAllocationChange: (label: string, value: number) => void;
}

export function AllocationDisplay({
  mode,
  amount,
  lumpDate,
  lumpTime,
  onLumpDateChange,
  onLumpTimeChange,
  periodStart,
  periodEnd,
  onPeriodStartChange,
  onPeriodEndChange,
  proportionalBasis,
  onProportionalBasisChange,
  manualDayLabels,
  manualAllocations,
  onManualAllocationChange,
}: AllocationDisplayProps) {
  if (mode === "lump_sum") {
    return (
      <div className="grid grid-cols-2 gap-3">
        <div>
          <label className="mb-1 block text-muted font-medium">Date</label>
          <input
            type="date"
            value={lumpDate}
            onChange={(e) => onLumpDateChange(e.target.value)}
            className="w-full rounded-md border border-border bg-bg-surface px-3 py-1.5 text-[12px] outline-none focus:border-muted-foreground"
          />
        </div>
        <div>
          <label className="mb-1 block text-muted font-medium">Time</label>
          <input
            type="time"
            value={lumpTime}
            onChange={(e) => onLumpTimeChange(e.target.value)}
            className="w-full rounded-md border border-border bg-bg-surface px-3 py-1.5 text-[12px] outline-none focus:border-muted-foreground"
          />
        </div>
      </div>
    );
  }

  if (mode === "even_daily") {
    return (
      <DateRangeFields
        startDate={periodStart}
        endDate={periodEnd}
        onStartChange={onPeriodStartChange}
        onEndChange={onPeriodEndChange}
      />
    );
  }

  if (mode === "proportional") {
    return (
      <>
        <DateRangeFields
          startDate={periodStart}
          endDate={periodEnd}
          onStartChange={onPeriodStartChange}
          onEndChange={onPeriodEndChange}
        />
        <div>
          <label className="mb-1 block text-muted font-medium">Proportional to</label>
          <select
            value={proportionalBasis}
            onChange={(e) => onProportionalBasisChange(e.target.value as "card" | "product")}
            className="w-full rounded-md border border-border bg-bg-surface px-3 py-1.5 text-[12px] outline-none focus:border-muted-foreground"
          >
            <option value="card">Total tracked costs for this card</option>
            <option value="product">Costs for selected product only</option>
          </select>
          <p className="mt-0.5 text-muted text-muted-foreground">
            Allocates more to days with higher existing costs, less to quieter days.
          </p>
        </div>
      </>
    );
  }

  // manual
  return (
    <>
      <DateRangeFields
        startDate={periodStart}
        endDate={periodEnd}
        onStartChange={onPeriodStartChange}
        onEndChange={onPeriodEndChange}
      />
      <ManualAllocation
        dayLabels={manualDayLabels}
        allocations={manualAllocations}
        targetAmount={Math.abs(amount)}
        onChange={onManualAllocationChange}
      />
    </>
  );
}
