import { createFileRoute, Outlet, redirect } from "@tanstack/react-router";
import { UserButton } from "@clerk/react";
import { User } from "lucide-react";
import { NavShell } from "@/components/shared/nav-shell";
import { WorkspaceError } from "@/components/shared/workspace-error";
import { noAuthMode } from "@/hooks/use-auth";
import { tenantConfigQueryOptions } from "@/hooks/use-tenant-config";
import { queryClient } from "@/lib/query-client";

export const Route = createFileRoute("/_app")({
  beforeLoad: async ({ context }) => {
    // Clerk signin check (skipped in no-auth dev mode).
    if (!noAuthMode && !context.auth?.isSignedIn) {
      throw redirect({ to: "/sign-in" });
    }

    // Workspace bootstrap: the tenant config gates products, billing mode,
    // and currency for every page. A failure here (401/403/network) renders
    // the workspace error screen instead of a broken shell.
    await queryClient.ensureQueryData(tenantConfigQueryOptions);
  },
  errorComponent: WorkspaceError,
  component: AppLayout,
});

function AppLayout() {
  const userSlot = !noAuthMode ? (
    <UserButton />
  ) : (
    <div className="flex h-7 w-7 items-center justify-center rounded-full bg-muted">
      <User className="h-4 w-4 text-muted-foreground" />
    </div>
  );

  return (
    <NavShell userSlot={userSlot}>
      <div className="p-6">
        <Outlet />
      </div>
    </NavShell>
  );
}
