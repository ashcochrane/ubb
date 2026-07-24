import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

/** House card shell for the billing sections (matches ChartCard's look). */
export function SectionCard({
  title,
  description,
  actions,
  children,
  className,
}: {
  title: string;
  description?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={cn(
        "rounded-md border border-border bg-bg-surface p-6 transition-colors hover:border-border-mid",
        className,
      )}
    >
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="text-[14px] font-semibold tracking-[-0.15px] text-text-primary">
            {title}
          </h2>
          {description && (
            <p className="mt-0.5 max-w-2xl text-[12px] text-text-secondary">{description}</p>
          )}
        </div>
        {actions && <div className="flex items-center gap-2">{actions}</div>}
      </div>
      {children}
    </section>
  );
}
