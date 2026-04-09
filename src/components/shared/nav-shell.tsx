import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { navSections } from "./nav-config";
import { TopBar } from "./top-bar";
import { useAuth } from "@/features/auth/hooks/use-auth";
import { cn } from "@/lib/utils";

interface NavShellProps {
  children: ReactNode;
  userSlot?: ReactNode;
}

export function NavShell({ children, userSlot }: NavShellProps) {
  const { isBillingMode } = useAuth();

  const visibleSections = navSections.filter(
    (section) =>
      !section.visibleWhen ||
      (section.visibleWhen === "billing" && isBillingMode),
  );

  return (
    <div className="flex h-screen bg-background">
      {/* Sidebar — full height, overlaps top bar area */}
      <aside className="flex w-56 shrink-0 flex-col border-r border-border">
        {/* Sidebar header — "UBB" branding, bottom border continues the top bar line */}
        <div className="flex h-11 items-center border-b border-border px-4">
          <span className="text-sm font-bold tracking-tight">UBB</span>
        </div>

        {/* Nav sections */}
        <nav className="flex-1 overflow-auto px-3 pt-3">
          {visibleSections.map((section, sectionIdx) => (
            <div
              key={section.label ?? sectionIdx}
              className={cn(sectionIdx > 0 && "mt-4")}
            >
              {section.label && (
                <div className="mb-1 px-2 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground">
                  {section.label}
                </div>
              )}
              <div className="space-y-0.5">
                {section.items.map((item) => (
                  <Link
                    key={item.url}
                    to={item.url}
                    className="flex items-center gap-2 rounded-md px-2 py-1 text-[12.5px] text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
                    activeProps={{
                      className:
                        "flex items-center gap-2 rounded-md px-2 py-1 text-[12.5px] font-medium bg-accent text-foreground",
                    }}
                    activeOptions={{ exact: item.url === "/" }}
                  >
                    <item.icon className="h-3.5 w-3.5 shrink-0" />
                    <span>{item.title}</span>
                  </Link>
                ))}
              </div>
            </div>
          ))}
        </nav>
      </aside>

      {/* Right side: top bar + content */}
      <div className="flex flex-1 flex-col overflow-hidden">
        <TopBar userSlot={userSlot} />
        <main className="flex-1 overflow-auto">{children}</main>
      </div>
    </div>
  );
}
