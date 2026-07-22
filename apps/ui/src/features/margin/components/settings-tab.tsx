import { ThresholdForm } from "./threshold-form";
import { BusinessLookup } from "./business-lookup";

export function SettingsTab({ currency }: { currency: string }) {
  return (
    <div className="space-y-6">
      <ThresholdForm />
      <BusinessLookup currency={currency} />
    </div>
  );
}
