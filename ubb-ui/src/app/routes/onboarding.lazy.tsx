import { createLazyFileRoute } from "@tanstack/react-router";
import { OnboardingLayout } from "@/features/onboarding/components/onboarding-layout";
import { OnboardingWizard } from "@/features/onboarding/components/onboarding-wizard";

export const Route = createLazyFileRoute("/onboarding")({
  component: OnboardingPage,
});

function OnboardingPage() {
  return (
    <OnboardingLayout>
      <OnboardingWizard />
    </OnboardingLayout>
  );
}
