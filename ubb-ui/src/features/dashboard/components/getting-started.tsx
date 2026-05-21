import { useState } from "react";
import { useMe } from "@/features/auth/api/queries";

const DISMISS_KEY = "getting-started:dismissed";

type ChecklistItem = {
  id: string;
  label: string;
  done: boolean;
  href?: string;
};

function getDismissed(): Set<string> {
  try {
    return new Set(JSON.parse(localStorage.getItem(DISMISS_KEY) || "[]"));
  } catch {
    return new Set();
  }
}

function saveDismissed(set: Set<string>) {
  localStorage.setItem(DISMISS_KEY, JSON.stringify([...set]));
}

export function GettingStarted() {
  const { data: me } = useMe();
  const [dismissed, setDismissed] = useState<Set<string>>(() => getDismissed());

  if (!me?.tenant) return null;

  const items: ChecklistItem[] = [
    {
      id: "create-card",
      label: "Create your first pricing card",
      done: me.tenant.pricingCardsCount > 0,
      href: "/pricing-cards/new",
    },
    {
      id: "send-event",
      label: "Send your first usage event",
      done: me.tenant.usageEventsCount > 0,
    },
    {
      id: "invite-teammate",
      label: "Invite a teammate (coming soon)",
      done: false,
    },
  ];

  const visible = items.filter((i) => !dismissed.has(i.id));
  if (visible.length === 0 || visible.every((i) => i.done)) return null;

  const dismiss = (id: string) => {
    const next = new Set(dismissed);
    next.add(id);
    setDismissed(next);
    saveDismissed(next);
  };

  return (
    <div className="rounded-lg border border-border bg-card p-4">
      <h3 className="mb-3 text-[13px] font-medium">Getting started</h3>
      <ul className="space-y-2">
        {visible.map((item) => (
          <li key={item.id} className="flex items-center gap-2 text-[12px]">
            <input type="checkbox" checked={item.done} disabled className="h-3 w-3" />
            {item.href && !item.done ? (
              <a href={item.href} className="flex-1 underline hover:no-underline">
                {item.label}
              </a>
            ) : (
              <span className={item.done ? "flex-1 line-through text-muted-foreground" : "flex-1"}>
                {item.label}
              </span>
            )}
            <button
              type="button"
              onClick={() => dismiss(item.id)}
              className="text-[11px] text-muted-foreground hover:text-foreground"
              aria-label={`Dismiss ${item.label}`}
            >
              ✕
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
