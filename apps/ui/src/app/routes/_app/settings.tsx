import { createFileRoute, Link, Outlet } from "@tanstack/react-router";

import { PageHeader } from "@/components/shared/page-header";
import { cn } from "@/lib/utils";

const SETTINGS_TABS: { title: string; to: string; exact?: boolean }[] = [
  { title: "Workspace", to: "/settings", exact: true },
  { title: "Team", to: "/settings/team" },
  { title: "Products", to: "/settings/products" },
  { title: "Your UBB bill", to: "/settings/billing" },
  { title: "Audit", to: "/settings/audit" },
];

export const Route = createFileRoute("/_app/settings")({
  component: SettingsLayout,
});

function SettingsLayout() {
  return (
    <div>
      <PageHeader
        title="Settings"
        description="Workspace configuration, team access, and account history."
      />
      <nav
        aria-label="Settings sections"
        className="mb-6 flex gap-1 border-b border-border"
      >
        {SETTINGS_TABS.map((tab) => (
          <Link
            key={tab.to}
            to={tab.to}
            activeOptions={{ exact: tab.exact ?? false }}
            className="-mb-px border-b-2 border-transparent px-3 py-2 text-[13px] text-text-secondary transition-colors hover:text-text-primary"
            activeProps={{
              className: cn(
                "-mb-px border-b-2 px-3 py-2 text-[13px] transition-colors",
                "border-text-primary font-semibold text-text-primary",
              ),
            }}
          >
            {tab.title}
          </Link>
        ))}
      </nav>
      <Outlet />
    </div>
  );
}
