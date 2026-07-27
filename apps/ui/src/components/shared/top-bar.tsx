import type { ReactNode } from "react";
import { Sun, User } from "lucide-react";
import { API_PROVIDER } from "@/lib/api-provider";
import { Brand } from "./brand";
import { IconButton } from "./icon-button";

interface TopBarProps {
  userSlot?: ReactNode;
}

export function TopBar({ userSlot }: TopBarProps) {
  const isMock = API_PROVIDER === "mock";

  return (
    <header className="flex h-[46px] shrink-0 items-center justify-between border-b border-border bg-bg-surface px-6">
      <div className="flex w-[200px] items-center">
        <Brand size="md" />
      </div>

      <div className="flex items-center gap-2">
        {isMock && (
          <span className="rounded-full border border-accent-border bg-accent-ghost px-2 py-[3px] text-[10px] font-bold uppercase tracking-[0.04em] text-accent-text">
            Mock
          </span>
        )}
        <IconButton aria-label="Appearance">
          <Sun className="h-[13px] w-[13px]" strokeWidth={1.5} />
        </IconButton>
        <IconButton aria-label="Account">
          <User className="h-[13px] w-[13px]" strokeWidth={1.5} />
        </IconButton>
        {userSlot}
      </div>
    </header>
  );
}
