import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/**
 * Bordered content section for a detail page — a heading, an optional line
 * under it, and the content.
 *
 * A layout primitive with no opinion about any feature, which is why it lives
 * here: the events feature carries its own copy from before this one existed,
 * and a third copy is where "sharing buys only a cross-feature edge" stops
 * being true. Named, so a test can scope its queries to one section with
 * `getByRole("region", { name })` — two concepts can share a word, and a
 * page-wide query cannot say which side it found.
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
