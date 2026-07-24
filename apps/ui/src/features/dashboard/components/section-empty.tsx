import { Link } from "@tanstack/react-router";

import { buttonVariants } from "@/components/ui/button";

/** Routes the overview's empty states can send the user to. */
export type SectionEmptyTo = "/developers" | "/pricing" | "/customers";

/**
 * Empty state with a navigation CTA. The shared <EmptyState> only takes an
 * onClick action; the overview's empty branches all navigate, so this local
 * variant renders a real link styled as a button instead of a dead handler.
 */
export function SectionEmpty({
  title,
  description,
  cta,
}: {
  title: string;
  description?: string;
  cta?: { label: string; to: SectionEmptyTo };
}) {
  return (
    <div className="flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed border-border p-10 text-center">
      <div className="text-sm font-medium text-text-primary">{title}</div>
      {description && (
        <p className="max-w-sm text-xs text-text-muted">{description}</p>
      )}
      {cta && (
        <Link
          to={cta.to}
          className={buttonVariants({ variant: "outline", size: "sm", className: "mt-2" })}
        >
          {cta.label}
        </Link>
      )}
    </div>
  );
}
