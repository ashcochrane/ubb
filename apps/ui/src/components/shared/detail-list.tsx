import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

export interface DetailItem {
  label: string;
  value: ReactNode;
  /** Render the value in monospace (ids, keys, technical values). */
  mono?: boolean;
}

/** Two-column label/value list for summary panels and detail pages. */
export function DetailList({
  items,
  className,
}: {
  items: DetailItem[];
  className?: string;
}) {
  return (
    <dl className={cn("divide-y divide-border", className)}>
      {items.map((item) => (
        <div
          key={item.label}
          className="flex items-baseline justify-between gap-4 py-2"
        >
          <dt className="shrink-0 text-[12px] text-text-secondary">{item.label}</dt>
          <dd
            className={cn(
              "min-w-0 break-words text-right text-[13px] text-text-primary",
              item.mono && "font-mono text-[12px]",
            )}
          >
            {item.value ?? "—"}
          </dd>
        </div>
      ))}
    </dl>
  );
}
