import type { ReactNode } from "react";
import { Link } from "@tanstack/react-router";
import { ArrowUpRight } from "lucide-react";

/** Responsive grid of raised StatCards used by every metric section. */
export function StatGrid({ children }: { children: ReactNode }) {
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
      {children}
    </div>
  );
}

/** A quiet "View →" affordance rendered in a Section's action slot. */
export function ViewLink({
  to,
  children,
}: {
  to: "/settings" | "/webhooks" | "/pricing" | "/customers" | "/margin" | "/billing" | "/usage";
  children: ReactNode;
}) {
  return (
    <Link
      to={to}
      className="inline-flex items-center gap-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
    >
      {children}
      <ArrowUpRight className="size-3.5" />
    </Link>
  );
}
