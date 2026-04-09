import { PanelLeft, Sun } from "lucide-react";
import type { ReactNode } from "react";
import { API_PROVIDER } from "@/lib/api-provider";

interface TopBarProps {
  userSlot?: ReactNode;
}

export function TopBar({ userSlot }: TopBarProps) {
  const isMock = API_PROVIDER === "mock";

  return (
    <header className="flex h-11 shrink-0 items-center gap-2 border-b border-border px-4">
      <button className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground">
        <PanelLeft className="h-4 w-4" />
      </button>

      <div className="flex-1" />

      {isMock && (
        <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-medium text-amber-700 dark:bg-amber-900/30 dark:text-amber-400">
          Mock
        </span>
      )}

      <button className="flex h-7 w-7 items-center justify-center rounded-md text-muted-foreground hover:bg-accent hover:text-foreground">
        <Sun className="h-4 w-4" />
      </button>

      {userSlot}
    </header>
  );
}
