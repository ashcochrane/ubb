import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";
import type { FilterOption } from "../api/types";

interface FilterPopoverProps {
  items: FilterOption[];
  selected: string;
  onPick: (key: string) => void;
  onClose: () => void;
  anchorRect: DOMRect | null;
  allLabel?: string;
}

export function FilterPopover({
  items,
  selected,
  onPick,
  onClose,
  anchorRect,
  allLabel,
}: FilterPopoverProps) {
  const [search, setSearch] = useState("");
  const ref = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        onClose();
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, [onClose]);

  const filtered = search
    ? items.filter((it) => it.key.toLowerCase().includes(search.toLowerCase()))
    : items;

  if (!anchorRect) return null;

  return (
    <div
      ref={ref}
      className="absolute z-50 min-w-[240px] rounded-md border border-border bg-bg-surface p-2 shadow-lg"
      style={{ left: anchorRect.left, top: anchorRect.bottom + 4 }}
    >
      <input
        ref={inputRef}
        className="mb-1.5 w-full rounded-sm border border-border-mid bg-bg-surface px-2.5 py-[5px] text-[11px] text-text-primary outline-none placeholder:text-text-muted focus:border-accent-dark focus:ring-2 focus:ring-accent-base/15"
        placeholder="Search..."
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />
      <div className="max-h-[160px] overflow-y-auto">
        {allLabel && (
          <button
            className={cn(
              "flex w-full items-center justify-between rounded-sm px-2.5 py-1.5 text-left text-[11px] transition-colors hover:bg-bg-subtle",
              selected === "" && "bg-accent-ghost",
            )}
            onClick={() => onPick("")}
          >
            <span className={cn("font-medium", selected === "" && "text-accent-text")}>
              {allLabel}
            </span>
          </button>
        )}
        {filtered.map((item) => (
          <button
            key={item.key}
            className={cn(
              "flex w-full items-center justify-between rounded-sm px-2.5 py-1.5 text-left text-[11px] transition-colors hover:bg-bg-subtle",
              selected === item.key && "bg-accent-ghost",
            )}
            onClick={() => onPick(item.key)}
          >
            <span className={cn("font-medium", selected === item.key && "text-accent-text")}>
              {item.key}
            </span>
            <span className="font-mono text-[9px] text-text-muted">
              {item.eventCount.toLocaleString()}
            </span>
          </button>
        ))}
        {search && filtered.length === 0 && (
          <button
            className="flex w-full items-center rounded-sm px-2.5 py-1.5 text-left text-[11px] transition-colors hover:bg-bg-subtle"
            onClick={() => onPick(search)}
          >
            <span className="font-medium text-accent-text">Use &quot;{search}&quot;</span>
          </button>
        )}
      </div>
      <div className="mt-1.5 flex justify-between border-t border-border pt-1.5">
        <button
          className="text-[10px] text-text-secondary hover:text-text-primary"
          onClick={onClose}
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
