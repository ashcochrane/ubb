import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { DateRange } from "../api/types";

/**
 * Shared start/end date control applied across the analytical margin tabs.
 * Values are ISO yyyy-mm-dd date strings the API accepts directly.
 */
export function DateRangeControl({
  value,
  onChange,
}: {
  value: DateRange;
  onChange: (range: DateRange) => void;
}) {
  return (
    <div className="flex flex-wrap items-end gap-3">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="margin-start-date">Start date</Label>
        <Input
          id="margin-start-date"
          type="date"
          className="w-[10.5rem]"
          value={value.start_date}
          max={value.end_date}
          onChange={(e) => onChange({ ...value, start_date: e.target.value })}
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="margin-end-date">End date</Label>
        <Input
          id="margin-end-date"
          type="date"
          className="w-[10.5rem]"
          value={value.end_date}
          min={value.start_date}
          onChange={(e) => onChange({ ...value, end_date: e.target.value })}
        />
      </div>
    </div>
  );
}
