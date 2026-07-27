import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  DATE_RANGE_PRESETS,
  matchPreset,
  resolveRange,
  type DateRange,
} from "@/lib/date-range";

/**
 * Preset + custom date-window control for analytics windows. Emits inclusive
 * YYYY-MM-DD dates as the API expects; clearing returns to month-to-date.
 */
export function DateRangePicker({
  value,
  onChange,
}: {
  value: DateRange;
  onChange: (range: DateRange) => void;
}) {
  const preset = matchPreset(value);
  const resolved = resolveRange(value);

  return (
    <div className="flex flex-wrap items-center gap-2">
      <Select
        value={preset}
        onValueChange={(key) => {
          if (key === "custom") return;
          const match = DATE_RANGE_PRESETS.find((p) => p.key === key);
          if (match) onChange(match.range());
        }}
      >
        <SelectTrigger className="h-8 w-[150px] text-[12px]" aria-label="Date range preset">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {DATE_RANGE_PRESETS.map((p) => (
            <SelectItem key={p.key} value={p.key}>
              {p.label}
            </SelectItem>
          ))}
          {preset === "custom" && <SelectItem value="custom">Custom</SelectItem>}
        </SelectContent>
      </Select>
      <div className="flex items-center gap-1">
        <Input
          type="date"
          value={resolved.start_date}
          max={resolved.end_date}
          aria-label="Start date"
          className="h-8 w-[140px] text-[12px]"
          onChange={(event) =>
            onChange({ start_date: event.target.value, end_date: resolved.end_date })
          }
        />
        <span className="text-[12px] text-text-muted">to</span>
        <Input
          type="date"
          value={resolved.end_date}
          min={resolved.start_date}
          aria-label="End date"
          className="h-8 w-[140px] text-[12px]"
          onChange={(event) =>
            onChange({ start_date: resolved.start_date, end_date: event.target.value })
          }
        />
      </div>
    </div>
  );
}
