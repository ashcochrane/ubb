import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/** Bordered content section used across the event receipt page. */
export function Section({
  title,
  description,
  children,
  className,
}: {
  title: string;
  description?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={cn(
        "rounded-md border border-border bg-bg-surface p-4",
        className,
      )}
    >
      <h2 className="text-[13px] font-semibold text-text-primary">{title}</h2>
      {description && (
        <p className="mt-0.5 text-[12px] text-text-secondary">{description}</p>
      )}
      <div className="mt-3">{children}</div>
    </section>
  );
}
