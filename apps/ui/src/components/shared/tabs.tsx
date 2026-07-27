import { useState, type ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface TabDef {
  value: string;
  label: string;
  /** Optional count/badge shown after the label. */
  badge?: ReactNode;
}

/**
 * Minimal monochrome tab bar (there is no shadcn tabs primitive in this repo).
 * Controlled if `value`/`onChange` are provided, otherwise self-managing from
 * `defaultValue`. Underline-style active indicator.
 */
export function TabBar({
  tabs,
  value,
  defaultValue,
  onChange,
  className,
}: {
  tabs: TabDef[];
  value?: string;
  defaultValue?: string;
  onChange?: (value: string) => void;
  className?: string;
}) {
  const [internal, setInternal] = useState(defaultValue ?? tabs[0]?.value);
  const active = value ?? internal;
  const select = (v: string) => {
    if (value === undefined) setInternal(v);
    onChange?.(v);
  };
  return (
    <div
      role="tablist"
      className={cn("flex items-center gap-4 border-b border-border", className)}
    >
      {tabs.map((tab) => {
        const isActive = tab.value === active;
        return (
          <button
            key={tab.value}
            role="tab"
            type="button"
            aria-selected={isActive}
            onClick={() => select(tab.value)}
            className={cn(
              "-mb-px flex items-center gap-1.5 border-b-2 px-0.5 pb-2 pt-1 text-sm transition-colors",
              isActive
                ? "border-foreground font-medium text-foreground"
                : "border-transparent text-muted-foreground hover:text-foreground",
            )}
          >
            {tab.label}
            {tab.badge != null && (
              <span className="text-xs text-muted-foreground">{tab.badge}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}

/** Convenience hook when you want simple in-page (non-URL) tab state. */
// eslint-disable-next-line react-refresh/only-export-components -- shared tab hook colocated with its component
export function useTabs(tabs: TabDef[], initial?: string) {
  const [active, setActive] = useState(initial ?? tabs[0]?.value);
  return { active, setActive };
}
