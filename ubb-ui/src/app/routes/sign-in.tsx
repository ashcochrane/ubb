import { createFileRoute, redirect } from "@tanstack/react-router";
import { SignIn } from "@clerk/react";
import { API_PROVIDER } from "@/lib/api-provider";

const noAuthMode = !import.meta.env.VITE_CLERK_PUBLISHABLE_KEY && API_PROVIDER === "mock";

export const Route = createFileRoute("/sign-in")({
  beforeLoad: ({ context }) => {
    if (noAuthMode || context.auth?.isSignedIn) {
      throw redirect({ to: "/" });
    }
  },
  component: SignInPage,
});

function SignInPage() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <SignIn routing="hash" fallbackRedirectUrl="/" />
    </div>
  );
}
