interface DateRangeFieldsProps {
  startDate: string;
  endDate: string;
  onStartChange: (value: string) => void;
  onEndChange: (value: string) => void;
}

export function DateRangeFields({ startDate, endDate, onStartChange, onEndChange }: DateRangeFieldsProps) {
  return (
    <div className="grid grid-cols-2 gap-3">
      <div>
        <label className="mb-1 block text-muted font-medium">Period start</label>
        <input
          type="date"
          value={startDate}
          onChange={(e) => onStartChange(e.target.value)}
          className="w-full rounded-md border border-border bg-bg-surface px-3 py-1.5 text-[12px] outline-none focus:border-muted-foreground"
        />
      </div>
      <div>
        <label className="mb-1 block text-muted font-medium">Period end</label>
        <input
          type="date"
          value={endDate}
          onChange={(e) => onEndChange(e.target.value)}
          className="w-full rounded-md border border-border bg-bg-surface px-3 py-1.5 text-[12px] outline-none focus:border-muted-foreground"
        />
      </div>
    </div>
  );
}
