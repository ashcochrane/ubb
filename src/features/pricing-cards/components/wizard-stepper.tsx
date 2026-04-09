import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

const steps = [
  { label: "Source" },
  { label: "Details" },
  { label: "Dimensions" },
  { label: "Review & test" },
];

interface WizardStepperProps {
  currentStep: number;
}

export function WizardStepper({ currentStep }: WizardStepperProps) {
  return (
    <div className="mb-6 flex items-center justify-center gap-0">
      {steps.map((step, idx) => {
        const isCompleted = idx < currentStep;
        const isActive = idx === currentStep;

        return (
          <div key={step.label} className="flex items-center">
            <div className="flex flex-col items-center">
              <div
                className={cn(
                  "flex h-6 w-6 items-center justify-center rounded-full border-2 text-[11px] font-medium transition-colors",
                  isCompleted && "border-green-600 bg-green-600 text-white",
                  isActive && "border-foreground text-foreground",
                  !isCompleted && !isActive && "border-border text-muted-foreground",
                )}
              >
                {isCompleted ? <Check className="h-3 w-3" /> : idx + 1}
              </div>
              <span className="mt-1 text-[10px] text-muted-foreground">
                {step.label}
              </span>
            </div>
            {idx < steps.length - 1 && (
              <div
                className={cn(
                  "mx-2 h-px w-10 transition-colors",
                  idx < currentStep ? "bg-green-600" : "bg-border",
                )}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
