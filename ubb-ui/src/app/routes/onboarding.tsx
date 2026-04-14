import { createFileRoute, redirect } from "@tanstack/react-router";
import { API_PROVIDER } from "@/lib/api-provider";

const noAuthMode = !import.meta.env.VITE_CLERK_PUBLISHABLE_KEY && API_PROVIDER === "mock";

export const Route = createFileRoute("/onboarding")({
  beforeLoad: ({ context }) => {
    if (!noAuthMode && !context.auth?.isSignedIn) {
      throw redirect({ to: "/sign-in" });
    }
  },
});
