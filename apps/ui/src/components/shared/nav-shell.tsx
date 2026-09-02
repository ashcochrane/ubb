import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { visibleNavSections } from "./nav-config";
import { TopBar } from "./top-bar";
import { useAuthUser } from "@/hooks/use-auth";
import { useCurrentRole } from "@/hooks/use-current-role";
import { useTenantConfig } from "@/hooks/use-tenant-config";
import { roleLabel } from "@/lib/labels";
import { cn } from "@/lib/utils";

interface NavShellProps {
  children: ReactNode;
  userSlot?: ReactNode;
}

// Shared layout base for sidebar nav links. Active/idle variants differ in
// color + weight only so keeping the base in one place avoids drift.
const NAV_LINK_BASE =
  "flex items-center gap-2 rounded-[6px] px-2.5 py-[5px] text-[12px] transition-colors";
const NAV_LINK_IDLE =
  "text-text-secondary hover:bg-bg-subtle hover:text-text-primary";
const NAV_LINK_ACTIVE = "bg-accent-ghost text-accent-text font-semibold";

export function NavShell({ children, userSlot }: NavShellProps) {
  const { data: config } = useTenantConfig();
  const user = useAuthUser();
  const { role } = useCurrentRole();

  // Product-gated navigation: never show a surface the tenant can't use.
  const visibleSections = visibleNavSections(config?.products);

  const initial = (user.name || user.email || "?").charAt(0).toUpperCase();

  return (
    <div className="grid h-screen grid-cols-[200px_1fr] grid-rows-[46px_1fr] bg-bg-page">
      {/* Topbar spans full width */}
      <div className="col-span-2 row-start-1">
        <TopBar userSlot={userSlot} tenantName={config?.name} />
      </div>

      {/* Sidebar (below topbar, fixed 200px) */}
      <aside
        aria-label="Primary navigation"
        className="col-start-1 row-start-2 flex flex-col border-r border-border bg-bg-surface py-4"
      >
        <nav className="flex-1 overflow-auto">
          {visibleSections.map((section, sectionIdx) => (
            <div key={section.label ?? sectionIdx} className={cn(sectionIdx > 0 && "mt-1")}>
              {section.label && (
                <div className="px-4 pt-[14px] pb-[5px] text-[9px] font-bold uppercase tracking-[0.08em] text-text-muted">
                  {section.label}
                </div>
              )}
              <div className="flex flex-col px-[6px]">
                {section.items.map((item) => (
                  <Link
                    key={item.url}
                    to={item.url}
                    className={cn(NAV_LINK_BASE, NAV_LINK_IDLE)}
                    activeProps={{
                      className: cn(NAV_LINK_BASE, NAV_LINK_ACTIVE),
                    }}
                    activeOptions={{ exact: item.url === "/" }}
                  >
                    <item.icon className="h-3.5 w-3.5 shrink-0 opacity-50" />
                    <span>{item.title}</span>
                  </Link>
                ))}
              </div>
            </div>
          ))}
        </nav>

        <div className="mt-auto border-t border-border px-4 py-[14px]">
          <div className="flex items-center gap-2">
            <div className="flex h-[26px] w-[26px] items-center justify-center rounded-full bg-accent-light text-[10px] font-bold text-accent-text">
              {initial}
            </div>
            <div className="min-w-0">
              <div className="truncate text-[12px] font-semibold">
                {user.name || user.email || "Signed in"}
              </div>
              <div className="text-[10px] text-text-muted">
                {role ? roleLabel(role) : " "}
              </div>
            </div>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="col-start-2 row-start-2 overflow-auto">{children}</main>
    </div>
  );
}
