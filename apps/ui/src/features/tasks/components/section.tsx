import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * Bordered content section used across the tasks pages.
 *
 * A local copy of the events feature's, on purpose: one feature never imports
 * another's components, and a section is small enough that sharing it would
 * buy a cross-feature edge and nothing else.
 */
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
      aria-label={title}
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
