import { useState } from "react";
import { useForm, FormProvider } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useNavigate } from "@tanstack/react-router";
import { onboardingSchema, type OnboardingFormValues } from "../lib/schema";
import { useCreateTenant, useCompleteOnboarding } from "../api/queries";
import { useMe } from "@/features/auth/api/queries";
import { Stepper } from "@/components/shared/stepper";
import { NameWorkspaceStep } from "./name-workspace-step";
import { CreateCardStep } from "./create-card-step";
import { SdkStep } from "./sdk-step";

const STEP_LABELS = ["Name workspace", "Create card", "Connect SDK"];

export function OnboardingWizard() {
  const navigate = useNavigate();
  const { data: me } = useMe();

  // If user has a tenant but onboarding isn't complete, resume at Step 2.
  const initialStep = me?.tenant ? 1 : 0;
  const [step, setStep] = useState(initialStep);
  const [apiKey, setApiKey] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const form = useForm<OnboardingFormValues>({
    resolver: zodResolver(onboardingSchema),
    defaultValues: { tenantName: "" },
    mode: "onChange",
  });

  const createTenant = useCreateTenant();
  const completeOnboarding = useCompleteOnboarding();

  const handleNameSubmit = async () => {
    setSubmitError(null);
    const valid = await form.trigger();
    if (!valid) return;
    const { tenantName } = form.getValues();
    try {
      const result = await createTenant.mutateAsync({ name: tenantName });
      setApiKey(result.apiKey);
      setStep(1);
    } catch (err) {
      setSubmitError(
        err instanceof Error
          ? `Couldn't create workspace: ${err.message}`
          : "Couldn't create workspace. Please retry."
      );
    }
  };

  const handleCardDone = () => setStep(2);
  const handleCardSkip = () => setStep(2);

  const handleFinalDone = async () => {
    try {
      await completeOnboarding.mutateAsync();
      navigate({ to: "/" });
    } catch {
      setSubmitError("Couldn't complete onboarding. Please retry.");
    }
  };

  return (
    <div>
      <Stepper
        steps={STEP_LABELS.map((label) => ({ label }))}
        currentIndex={step}
        className="mb-6"
      />
      <FormProvider {...form}>
        {step === 0 && (
          <NameWorkspaceStep
            onSubmit={handleNameSubmit}
            isSubmitting={createTenant.isPending}
            error={submitError}
          />
        )}
        {step === 1 && (
          <CreateCardStep onSuccess={handleCardDone} onSkip={handleCardSkip} />
        )}
        {step === 2 && (
          <SdkStep
            apiKey={apiKey}
            onDone={handleFinalDone}
            isCompleting={completeOnboarding.isPending}
          />
        )}
      </FormProvider>
    </div>
  );
}
