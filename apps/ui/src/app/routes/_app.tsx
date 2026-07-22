import { createFileRoute, Outlet, redirect } from "@tanstack/react-router";
import { UserButton } from "@clerk/react";
import { User } from "lucide-react";
import { NavShell } from "@/components/shared/nav-shell";
import { RouteError } from "@/components/shared/route-error";
import { API_PROVIDER } from "@/lib/api-provider";
import { queryClient } from "@/lib/query-client";
import { meQueryOptions } from "@/features/auth/api/queries";

const noAuthMode = !import.meta.env.VITE_CLERK_PUBLISHABLE_KEY && API_PROVIDER === "mock";

export const Route = createFileRoute("/_app")({
  beforeLoad: async ({ context }) => {
    // Clerk signin check (skipped in no-auth dev mode)
    if (!noAuthMode && !context.auth?.isSignedIn) {
      throw redirect({ to: "/sign-in" });
    }

    // Load tenant context (products, billing mode, Stripe connection). A failure
    // here (e.g. no tenant provisioned) surfaces via the route errorComponent.
    await queryClient.ensureQueryData(meQueryOptions);
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
