import { createFileRoute, redirect } from "@tanstack/react-router";
import { API_PROVIDER } from "@/lib/api-provider";
import { queryClient } from "@/lib/query-client";
import { meQueryOptions } from "@/features/auth/api/queries";

const noAuthMode = !import.meta.env.VITE_CLERK_PUBLISHABLE_KEY && API_PROVIDER === "mock";

export const Route = createFileRoute("/onboarding")({
  beforeLoad: async ({ context }) => {
    if (!noAuthMode && !context.auth?.isSignedIn) {
      throw redirect({ to: "/sign-in" });
    }
    const me = await queryClient.ensureQueryData(meQueryOptions);
    if (me.tenantUser && me.onboardingCompleted) {
      throw redirect({ to: "/" });
    }
  },
});
