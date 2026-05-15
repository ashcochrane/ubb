import { useState } from "react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Popover,
  PopoverTrigger,
  PopoverContent,
} from "@/components/ui/popover";
import { X } from "lucide-react";
import type { FilterOptionCustomer } from "../api/types";

interface CustomerMultiSelectProps {
  customers: FilterOptionCustomer[];
  selectedIds: string[];
  onSelectionChange: (ids: string[]) => void;
}

export function CustomerMultiSelect({
  customers,
  selectedIds,
  onSelectionChange,
}: CustomerMultiSelectProps) {
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState(false);
  const isAll = selectedIds.length === 0;

  const filtered = customers.filter((c) =>
    c.name.toLowerCase().includes(search.toLowerCase()),
  );

  function toggleCustomer(id: string) {
    if (selectedIds.includes(id)) {
      onSelectionChange(selectedIds.filter((i) => i !== id));
    } else {
      onSelectionChange([...selectedIds, id]);
    }
  }

  function removeCustomer(id: string) {
    onSelectionChange(selectedIds.filter((i) => i !== id));
  }

  return (
    <div>
      <div className="mb-2 text-[12px] font-semibold text-text-primary">Customers</div>
      <div className="mb-1 flex items-center gap-1.5">
        <button
          className={cn(
            "inline-flex items-center gap-1 rounded-full border px-3 py-1 text-[12px] font-medium",
            isAll
              ? "border-accent-base bg-accent-base text-text-inverse"
              : "border-border-mid bg-bg-surface text-text-secondary hover:bg-bg-subtle hover:text-text-primary",
          )}
          onClick={() => onSelectionChange([])}
        >
          All customers
          <span className="text-tiny opacity-60">({customers.length})</span>
        </button>
        <span className="text-[11px] text-text-muted">
          or select specific:
        </span>
      </div>

      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger
          render={
            <input
              type="text"
              placeholder="Search customers..."
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                if (!open) setOpen(true);
              }}
              onFocus={() => setOpen(true)}
              className="w-full rounded-sm border border-border bg-bg-surface px-2.5 py-1.5 text-[12px] font-medium text-foreground placeholder:text-muted-foreground hover:border-ring focus:border-accent-dark focus:ring-2 focus:ring-accent-base/15 focus:outline-none"
            />
          }
        />
        <PopoverContent
          className="w-[var(--anchor-width)] p-0"
          align="start"
          sideOffset={4}
        >
          <ScrollArea className="max-h-[200px]">
            {filtered.map((c) => {
              const checked = selectedIds.includes(c.id);
              return (
                <button
                  key={c.id}
                  type="button"
                  className="flex w-full items-center justify-between px-3 py-1.5 text-[12px] font-medium hover:bg-bg-subtle"
                  onClick={() => toggleCustomer(c.id)}
                >
                  <div className="flex items-center gap-1.5">
                    <div
                      className={cn(
                        "flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-[3px] border-[1.5px]",
                        checked
                          ? "border-accent-base bg-accent-base"
                          : "border-border",
                      )}
                    >
                      {checked && (
                        <svg width="8" height="8" viewBox="0 0 8 8" fill="none">
                          <path
                            d="M1.5 4L3 5.5L6.5 2"
                            stroke="currentColor"
                            className="text-primary-foreground"
                            strokeWidth="1.5"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                        </svg>
                      )}
                    </div>
                    <span className="font-medium">{c.name}</span>
                  </div>
                  <span className="font-mono text-tiny text-muted-foreground">
                    {c.eventCount.toLocaleString()} evts
                  </span>
                </button>
              );
            })}
            {filtered.length === 0 && (
              <div className="px-3 py-2 text-label text-muted-foreground">
                No customers match your search.
              </div>
            )}
          </ScrollArea>
        </PopoverContent>
      </Popover>

      {selectedIds.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {selectedIds.map((id) => {
            const customer = customers.find((c) => c.id === id);
            if (!customer) return null;
            return (
              <Badge key={id} variant="secondary" className="gap-1 text-muted">
                {customer.name}
                <button
                  type="button"
                  onClick={() => removeCustomer(id)}
                  className="opacity-50 hover:opacity-100"
                >
                  <X className="h-3 w-3" />
                </button>
              </Badge>
            );
          })}
        </div>
      )}
    </div>
  );
}
