import { useState, useCallback } from "react";
import { useForm, FormProvider } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useNavigate } from "@tanstack/react-router";
import { onboardingSchema, type OnboardingFormValues } from "../lib/schema";
import type { OnboardingMode } from "../api/types";
import { MOCK_TENANT_ID } from "../lib/constants";
import { Stepper } from "@/components/shared/stepper";
import { ModeSelector } from "./mode-selector";
import { StripeKeyStep } from "./stripe-key-step";
import { CustomerMappingStep } from "./customer-mapping-step";
import { MarginConfigStep } from "./margin-config-step";
import { ReviewStep } from "./review-step";
import { ActivationSuccess } from "./activation-success";
import { useAuthStore } from "@/stores/auth-store";

const defaultValues: OnboardingFormValues = {
  mode: "revenue",
  stripeKey: "",
  keyValidated: false,
  identifierMode: undefined,
  metadataKey: "",
  mappingComplete: false,
  matchResult: null,
  defaultMargin: 50,
  notifyAt: 50,
  remindAt: 25,
  pauseAtZero: false,
};

function getSteps(mode: OnboardingMode): string[] {
  switch (mode) {
    case "track":
      return ["Choose mode"];
    case "revenue":
      return ["Choose mode", "Connect Stripe", "Map customers", "Review"];
    case "billing":
      return ["Choose mode", "Connect Stripe", "Map customers", "Configure billing", "Review"];
  }
}

export function OnboardingWizard() {
  const [step, setStep] = useState(0);
  const [activated, setActivated] = useState(false);
  const [activatedMode, setActivatedMode] = useState<OnboardingMode>("revenue");
  const navigate = useNavigate();

  const form = useForm<OnboardingFormValues>({
    resolver: zodResolver(onboardingSchema),
    defaultValues,
    mode: "onChange",
  });

  const mode = form.watch("mode");
  const steps = getSteps(mode);

  const next = useCallback(() => {
    if (step === 0 && mode === "track") {
      const tenantId = useAuthStore.getState().activeTenantId ?? MOCK_TENANT_ID;
      useAuthStore.getState().setTenant(tenantId, "track");
      navigate({ to: "/pricing-cards/new" });
      return;
    }
    setStep((s) => Math.min(s + 1, steps.length - 1));
  }, [step, mode, steps.length, navigate]);

  const prev = useCallback(() => {
    setStep((s) => Math.max(s - 1, 0));
  }, []);

  const goToStep = useCallback((targetStep: number) => {
    setStep(targetStep);
  }, []);

  const handleActivated = useCallback(() => {
    const tenantMode = mode === "billing" ? "billing" : "revenue";
    const tenantId = useAuthStore.getState().activeTenantId ?? MOCK_TENANT_ID;
    useAuthStore.getState().setTenant(tenantId, tenantMode);
    setActivatedMode(mode);
    setActivated(true);
  }, [mode]);

  const canAdvance = (): boolean => {
    if (step === 0) return true;
    const stepsAfterMode = step - 1;
    if (stepsAfterMode === 0) return form.getValues("keyValidated");
    if (stepsAfterMode === 1) return form.getValues("mappingComplete");
    return true;
  };

  const renderStep = () => {
    if (activated) return <ActivationSuccess mode={activatedMode} />;
    if (step === 0) return <ModeSelector />;

    const stepsAfterMode = step - 1;

    if (mode === "revenue") {
      switch (stepsAfterMode) {
        case 0: return <StripeKeyStep />;
        case 1: return <CustomerMappingStep />;
        case 2: return <ReviewStep onActivated={handleActivated} onEditStep={goToStep} />;
      }
    }

    if (mode === "billing") {
      switch (stepsAfterMode) {
        case 0: return <StripeKeyStep />;
        case 1: return <CustomerMappingStep />;
        case 2: return <MarginConfigStep />;
        case 3: return <ReviewStep onActivated={handleActivated} onEditStep={goToStep} />;
      }
    }

    return null;
  };

  const isReviewStep = step === steps.length - 1 && step > 0;

  return (
    <div>
      {!activated && (
        <Stepper
          steps={steps.map((label) => ({ label }))}
          currentIndex={step}
          className="mb-6"
        />
      )}

      <FormProvider {...form}>
        {renderStep()}
      </FormProvider>

      {!activated && !isReviewStep && (
        <div className="mt-6 flex justify-between">
          {step > 0 ? (
            <button
              type="button"
              onClick={prev}
              className="rounded-lg border border-border px-4 py-2 text-[12px] text-muted-foreground hover:bg-accent"
            >
              Back
            </button>
          ) : (
            <div />
          )}
          <button
            type="button"
            onClick={next}
            disabled={!canAdvance()}
            className="rounded-lg bg-foreground px-5 py-2 text-[12px] font-medium text-background hover:opacity-90 disabled:opacity-50"
          >
            {step === 0 && mode === "track" ? "Continue to pricing cards" : "Continue"}
          </button>
        </div>
      )}
    </div>
  );
}
