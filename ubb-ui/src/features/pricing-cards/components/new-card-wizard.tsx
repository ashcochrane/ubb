import { useState, useCallback } from "react";
import { useForm, FormProvider } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useNavigate } from "@tanstack/react-router";
import { Stepper } from "@/components/shared/stepper";
import { StepSource } from "./step-source";
import { StepDetails } from "./step-details";
import { StepDimensions } from "./step-dimensions";
import { StepReview } from "./step-review";
import { wizardSchema, type WizardFormValues } from "../lib/schema";
import { useTemplates } from "../api/queries";

const defaultValues: WizardFormValues = {
  sourceType: "template",
  templateId: undefined,
  name: "",
  provider: "",
  providerCustom: undefined,
  cardId: "",
  pricingPattern: "token",
  description: "",
  pricingSourceUrl: "",
  dimensions: [],
  product: undefined,
};

export function NewCardWizard() {
  const [step, setStep] = useState(0);
  const navigate = useNavigate();
  const { data: templates = [] } = useTemplates();

  const form = useForm<WizardFormValues>({
    resolver: zodResolver(wizardSchema),
    defaultValues,
    mode: "onChange",
  });

  const [stepError, setStepError] = useState<string | null>(null);

  const next = useCallback(() => {
    setStepError(null);

    if (step === 0) {
      const sourceType = form.getValues("sourceType");
      const templateId = form.getValues("templateId");

      // Validate: template mode requires a template selection
      if (sourceType === "template" && !templateId) {
        setStepError("Please select a template.");
        return;
      }

      if (sourceType === "template" && templateId) {
        const template = templates.find((t) => t.id === templateId);
        if (template) {
          form.setValue("name", template.name);
          form.setValue("provider", template.provider);
          form.setValue("pricingPattern", template.pricingPattern);
          form.setValue("dimensions", structuredClone(template.dimensions));
          form.setValue("description", template.description ?? "");
        }
      }
    }

    if (step === 1) {
      const name = form.getValues("name");
      const provider = form.getValues("provider");
      const cardId = form.getValues("cardId");
      if (!name.trim()) { setStepError("Card name is required."); return; }
      if (!provider.trim()) { setStepError("Provider is required."); return; }
      if (!cardId.trim()) { setStepError("Card ID is required."); return; }
    }

    if (step === 2) {
      const dimensions = form.getValues("dimensions");
      if (dimensions.length === 0) { setStepError("Add at least one dimension."); return; }
      if (dimensions.some((d) => !d.key.trim())) { setStepError("All dimensions need a metric key."); return; }
    }

    setStep((s) => Math.min(s + 1, 3));
  }, [step, form, templates]);

  const prev = useCallback(() => {
    setStep((s) => Math.max(s - 1, 0));
  }, []);

  const goToCards = useCallback(() => {
    navigate({ to: "/pricing-cards" });
  }, [navigate]);

  return (
    <div className="mx-auto max-w-[640px]">
      <Stepper
        steps={[
          { label: "Source" },
          { label: "Details" },
          { label: "Dimensions" },
          { label: "Review & test" },
        ]}
        currentIndex={step}
        className="mb-6"
      />

      <FormProvider {...form}>
        {step === 0 && <StepSource />}
        {step === 1 && <StepDetails />}
        {step === 2 && <StepDimensions />}
        {step === 3 && <StepReview />}
      </FormProvider>

      {stepError && (
        <p className="mt-3 text-center text-[12px] text-red">{stepError}</p>
      )}

      <div className="mt-4 flex justify-between">
        {step > 0 ? (
          <button
            type="button"
            onClick={prev}
            className="rounded-md border border-border px-4 py-1.5 text-[12.5px] text-muted-foreground hover:bg-accent"
          >
            Back
          </button>
        ) : (
          <button
            type="button"
            onClick={goToCards}
            className="rounded-md border border-border px-4 py-1.5 text-[12.5px] text-muted-foreground hover:bg-accent"
          >
            Cancel
          </button>
        )}
        {step < 3 && (
          <button
            type="button"
            onClick={next}
            className="rounded-md bg-foreground px-5 py-1.5 text-[12.5px] font-medium text-background hover:opacity-90"
          >
            Next
          </button>
        )}
      </div>
    </div>
  );
}
