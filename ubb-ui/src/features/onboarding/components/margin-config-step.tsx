// src/features/onboarding/components/margin-config-step.tsx
import { useState } from "react";
import { useFormContext } from "react-hook-form";
import type { OnboardingFormValues } from "../lib/schema";

export function MarginConfigStep() {
  const { watch, setValue } = useFormContext<OnboardingFormValues>();
  const defaultMargin = watch("defaultMargin");
  const [exampleCost, setExampleCost] = useState(2.0);

  const chargeAmount = exampleCost * (1 + defaultMargin / 100);
  const profit = chargeAmount - exampleCost;

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-[16px] font-semibold">Configure billing</h2>
        <p className="mt-1 text-[12px] text-muted-foreground">
          Set a default margin percentage that applies to all API costs. You can override per product or per pricing card later.
        </p>
      </div>

      {/* Margin slider */}
      <div>
        <div className="mb-2 flex items-center justify-between">
          <label className="text-label font-medium">Default margin</label>
          <span className="text-[14px] font-semibold">{defaultMargin}%</span>
        </div>
        <input
          type="range"
          min={0}
          max={200}
          step={5}
          value={defaultMargin}
          onChange={(e) => setValue("defaultMargin", Number(e.target.value))}
          className="w-full accent-foreground"
        />
        <p className="mt-1 text-muted text-muted-foreground">
          {defaultMargin}% margin means ${exampleCost.toFixed(2)} API cost becomes ${chargeAmount.toFixed(2)} charged to your customer.
        </p>
      </div>

      {/* Billing preview */}
      <div className="rounded-xl bg-accent/50 px-4 py-4">
        <div className="mb-3 text-label font-medium">Billing preview</div>

        <div className="mb-3">
          <label className="mb-1 block text-muted text-muted-foreground">Try different API cost</label>
          <input
            type="range"
            min={0.1}
            max={5}
            step={0.1}
            value={exampleCost}
            onChange={(e) => setExampleCost(Number(e.target.value))}
            className="w-full accent-foreground"
          />
        </div>

        <div className="grid grid-cols-3 gap-2 text-center">
          <div className="rounded-lg bg-background px-3 py-3">
            <div className="text-[18px] font-semibold">${exampleCost.toFixed(2)}</div>
            <div className="text-muted text-muted-foreground">API cost</div>
          </div>
          <div className="rounded-lg bg-background px-3 py-3">
            <div className="text-[18px] font-semibold">+${profit.toFixed(2)}</div>
            <div className="text-muted text-muted-foreground">Your margin ({defaultMargin}%)</div>
          </div>
          <div className="rounded-lg bg-background px-3 py-3">
            <div className="text-[18px] font-semibold">${chargeAmount.toFixed(2)}</div>
            <div className="text-muted text-muted-foreground">Customer charged</div>
          </div>
        </div>
      </div>

    </div>
  );
}
