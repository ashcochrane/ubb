import { createFileRoute, Outlet, redirect } from "@tanstack/react-router";
import { UserButton } from "@clerk/react";
import { User } from "lucide-react";
import { NavShell } from "@/components/shared/nav-shell";
import { RouteError } from "@/components/shared/route-error";
import { useAuthStore } from "@/stores/auth-store";
import { API_PROVIDER } from "@/lib/api-provider";

const noAuthMode = !import.meta.env.VITE_CLERK_PUBLISHABLE_KEY && API_PROVIDER === "mock";

export const Route = createFileRoute("/_app")({
  beforeLoad: async ({ context }) => {
    // No-auth dev mode: only when mock provider AND no Clerk key
    if (noAuthMode) {
      const { activeTenantId } = useAuthStore.getState();
      if (!activeTenantId) {
        useAuthStore.getState().setTenant("tenant-mock-001", "billing");
      }
      return;
    }

    // Real auth: check Clerk
    if (!context.auth?.isSignedIn) {
      throw redirect({ to: "/sign-in" });
    }

    // TODO (Phase 7 - API Integration): Fetch tenant context from backend
    // and call useAuthStore.getState().setTenant(tenantId, mode) here.
    // Until then, Clerk-authenticated users will have empty tenant state.
  },
  errorComponent: RouteError,
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
