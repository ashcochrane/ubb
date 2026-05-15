import { createLazyFileRoute } from "@tanstack/react-router";
import { OnboardingWizard } from "@/features/onboarding/components/onboarding-wizard";

export const Route = createLazyFileRoute("/onboarding")({
  component: OnboardingPage,
});

function OnboardingPage() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="w-full max-w-md px-4">
        <OnboardingWizard />
      </div>
    </div>
  );
}
