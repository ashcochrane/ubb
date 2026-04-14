import { useState } from "react";

const COLUMNS = ["date", "customer", "group", "pricing_card", "dimension", "quantity"];

interface PasteAreaProps {
  onParse: (rows: string[][]) => void;
  onCancel: () => void;
}

export function PasteArea({ onParse, onCancel }: PasteAreaProps) {
  const [value, setValue] = useState("");

  function handleParse() {
    const raw = value.trim();
    if (!raw) return;
    const parsed = raw
      .split("\n")
      .filter((l) => l.trim())
      .map((l) => l.split("\t"))
      .filter((parts) => parts.length >= 6);
    onParse(parsed);
  }

  return (
    <div className="rounded-md border border-accent-border bg-accent-ghost px-4 py-3.5">
      <div className="mb-1.5 text-[12px] font-semibold text-accent-text">
        Paste tab-separated data
      </div>
      <div className="mb-2 flex flex-wrap items-center gap-1 text-[9px] text-text-secondary">
        Columns:{" "}
        {COLUMNS.map((col) => (
          <span
            key={col}
            className="rounded border border-accent-border bg-bg-surface px-1.5 py-px font-mono text-accent-text"
          >
            {col}
          </span>
        ))}
      </div>
      <textarea
        className="w-full rounded-sm border border-border-mid bg-bg-surface px-2.5 py-2 font-mono text-[10px] leading-[1.8] text-text-primary outline-none focus:border-accent-dark focus:ring-2 focus:ring-accent-base/15"
        rows={4}
        placeholder={`2026-03-15\tacme_corp\tresearch_agent\tgemini_2_flash\tinput_tokens\t4200\n2026-03-15\tacme_corp\tresearch_agent\tgemini_2_flash\toutput_tokens\t1800`}
        value={value}
        onChange={(e) => setValue(e.target.value)}
      />
      <div className="mt-2 flex justify-between">
        <button
          className="rounded-full border border-border-mid bg-bg-surface px-3 py-1 text-[11px] text-text-secondary hover:bg-bg-subtle"
          onClick={onCancel}
        >
          Cancel
        </button>
        <button
          className="rounded-full bg-accent-base px-4 py-1 text-[11px] font-medium text-text-inverse hover:bg-accent-hover"
          onClick={handleParse}
        >
          Load into staging grid
        </button>
      </div>
    </div>
  );
}
