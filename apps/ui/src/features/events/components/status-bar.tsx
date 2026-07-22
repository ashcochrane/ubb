import { formatCostMicros } from "@/lib/format";

interface StatusBarProps {
  totalCount: number;
  totalCostMicros: number;
  showRecorded: boolean;
  onToggleRecorded: () => void;
}

export function StatusBar({
  totalCount,
  totalCostMicros,
  showRecorded,
  onToggleRecorded,
}: StatusBarProps) {
  return (
    <div className="flex items-center justify-between border-b border-border py-2 text-[11px] text-text-secondary">
      <div className="flex items-center gap-4">
        <span className="text-[12px] font-semibold text-text-primary">
          {totalCount.toLocaleString()} rows
        </span>
        <span className="font-mono">
          {formatCostMicros(totalCostMicros)} total
        </span>
      </div>
      <button
        className="flex cursor-pointer select-none items-center gap-2 text-[10px] text-text-secondary"
        onClick={onToggleRecorded}
      >
        <div className={`relative h-[15px] w-[28px] rounded-full transition-colors ${showRecorded ? "bg-accent-base" : "bg-border-mid"}`}>
          <div className={`absolute top-[2px] h-[11px] w-[11px] rounded-full bg-white transition-[left] ${showRecorded ? "left-[15px]" : "left-[2px]"}`} />
        </div>
        <span>Also show data as recorded</span>
      </button>
    </div>
  );
}
