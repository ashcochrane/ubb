import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

export interface StepperProps {
  steps: Array<{ label: string }>;
  currentIndex: number;
  className?: string;
}

/**
 * Shared stepper used by the pricing card wizard and the onboarding flow.
 * Renders a horizontal numbered list of steps where completed steps show
 * a check mark and the current step is outlined.
 */
export function Stepper({ steps, currentIndex, className }: StepperProps) {
  return (
    <div
      data-slot="stepper"
      className={cn("flex items-center justify-center", className)}
    >
      {steps.map((step, idx) => {
        const completed = idx < currentIndex;
        const active = idx === currentIndex;

        return (
          <div key={step.label} className="flex items-center">
            <div className="flex flex-col items-center">
              <div
                data-state={
                  completed ? "completed" : active ? "active" : "pending"
                }
                className={cn(
                  "flex h-7 w-7 items-center justify-center rounded-full text-label font-semibold transition-colors",
                  completed && "bg-foreground text-background",
                  active && "border-2 border-foreground text-foreground",
                  !completed &&
                    !active &&
                    "border border-border text-muted-foreground",
                )}
              >
                {completed ? (
                  <Check className="h-3.5 w-3.5" data-testid="stepper-check" />
                ) : (
                  idx + 1
                )}
              </div>
              <span className="mt-1.5 text-muted text-muted-foreground">
                {step.label}
              </span>
            </div>
            {idx < steps.length - 1 && (
              <div
                className={cn(
                  "mx-3 h-px w-12 transition-colors",
                  completed ? "bg-foreground" : "bg-border",
                )}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
