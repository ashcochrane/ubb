import { Link } from "@tanstack/react-router";

import { cn } from "@/lib/utils";

/**
 * The two surfaces of the Tasks tab, side by side.
 *
 * Kinds of work are the front door and runs are their sibling — never the other
 * way round (#423, #424; spec §25 Q2): a tenant looking here is looking at how
 * their business sells first, and at what ran second. Both pages render this,
 * so the two are one tab rather than a page with a link on it.
 */
export function TasksNav({ current }: { current: "kinds" | "runs" }) {
  return (
    <nav aria-label="Tasks" className="flex gap-1 border-b border-border">
      <Link
        to="/tasks"
        className={tabClass(current === "kinds")}
        aria-current={current === "kinds" ? "page" : undefined}
      >
        Kinds of work
      </Link>
      <Link
        to="/tasks/runs"
        className={tabClass(current === "runs")}
        aria-current={current === "runs" ? "page" : undefined}
      >
        Runs
      </Link>
    </nav>
  );
}

function tabClass(active: boolean): string {
  return cn(
    "-mb-px border-b-2 px-3 py-2 text-[12px] font-medium",
    active
      ? "border-text-primary text-text-primary"
      : "border-transparent text-text-secondary hover:text-text-primary",
  );
}
