import { cn } from "@/lib/utils";

interface PillOption {
  key: string;
  label: string;
  percentage: number;
}

interface TogglePillGroupProps {
  label: string;
  allLabel: string; // "All products" or "All cards"
  options: PillOption[];
  selectedKeys: string[];
  onSelectionChange: (keys: string[]) => void;
}

export function TogglePillGroup({
  label,
  allLabel,
  options,
  selectedKeys,
  onSelectionChange,
}: TogglePillGroupProps) {
  const isAll = selectedKeys.length === 0;

  function toggleKey(key: string) {
    if (selectedKeys.includes(key)) {
      const next = selectedKeys.filter((k) => k !== key);
      onSelectionChange(next); // empty = all
    } else {
      onSelectionChange([...selectedKeys, key]);
    }
  }

  return (
    <div>
      <div className="mb-2 text-[12px] font-semibold text-text-primary">{label}</div>
      <div className="flex flex-wrap gap-1.5">
        <button
          className={cn(
            "inline-flex items-center gap-1 rounded-full border px-3 py-1 text-[12px] font-medium",
            isAll
              ? "border-accent-base bg-accent-base text-text-inverse"
              : "border-border-mid bg-bg-surface text-text-secondary hover:bg-bg-subtle hover:text-text-primary",
          )}
          onClick={() => onSelectionChange([])}
        >
          {allLabel}
        </button>
        {options.map((opt) => {
          const active = selectedKeys.includes(opt.key);
          return (
            <button
              key={opt.key}
              className={cn(
                "inline-flex items-center gap-1 rounded-full border px-3 py-1 text-[12px] font-medium",
                active
                  ? "border-accent-base bg-accent-base text-text-inverse"
                  : "border-border-mid bg-bg-surface text-text-secondary hover:bg-bg-subtle hover:text-text-primary",
              )}
              onClick={() => toggleKey(opt.key)}
            >
              {opt.label}
              <span className="text-tiny opacity-60">{opt.percentage}%</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
