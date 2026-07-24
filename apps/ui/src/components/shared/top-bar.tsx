import type { ReactNode } from "react";
import { API_PROVIDER } from "@/lib/api-provider";
import { Brand } from "./brand";

interface TopBarProps {
  userSlot?: ReactNode;
  tenantName?: string;
}

export function TopBar({ userSlot, tenantName }: TopBarProps) {
  const isMock = API_PROVIDER === "mock";

  return (
    <header className="flex h-[46px] shrink-0 items-center justify-between border-b border-border bg-bg-surface px-6">
      <div className="flex items-center gap-3">
        <div className="flex w-[176px] items-center">
          <Brand size="md" />
        </div>
        {tenantName && (
          <span className="border-l border-border pl-3 text-[12px] font-medium text-text-secondary">
            {tenantName}
          </span>
        )}
      </div>

      <div className="flex items-center gap-2">
        {isMock && (
          <span className="rounded-full border border-accent-border bg-accent-ghost px-2 py-[3px] text-[10px] font-bold uppercase tracking-[0.04em] text-accent-text">
            Mock
          </span>
        )}
        {userSlot}
      </div>
    </header>
  );
}
