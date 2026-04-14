import { useFormContext } from "react-hook-form";
import { BarChart3, TrendingUp, CreditCard } from "lucide-react";
import type { OnboardingFormValues } from "../lib/schema";
import type { OnboardingMode } from "../api/types";
import { cn } from "@/lib/utils";

interface ModeOption {
  value: OnboardingMode;
  icon: React.ElementType;
  title: string;
  subtitle: string;
  features: string[];
  badge?: { label: string; color: string };
  stripeNeeded: string;
}

const modes: ModeOption[] = [
  {
    value: "track",
    icon: BarChart3,
    title: "Track costs",
    subtitle: "Monitor API costs per customer, per product. No revenue data.",
    features: ["Pricing cards + SDK", "Cost dashboard", "Data export"],
    stripeNeeded: "No Stripe needed",
  },
  {
    value: "revenue",
    icon: TrendingUp,
    title: "Revenue and costs",
    subtitle: "Pull revenue from Stripe and pair it with tracked costs to show profitability.",
    features: ["Everything in Track costs", "Stripe revenue sync", "Profitability dashboard"],
    stripeNeeded: "Stripe (read-only)",
  },
  {
    value: "billing",
    icon: CreditCard,
    title: "Bill your customers",
    subtitle: "Everything above, plus debit customer Stripe balances for each API event.",
    features: ["Everything in Revenue + costs", "Balance debiting", "Margin management", "Balance alerts"],
    stripeNeeded: "Stripe (read + write)",
  },
];

export function ModeSelector() {
  const { watch, setValue } = useFormContext<OnboardingFormValues>();
  const selectedMode = watch("mode");

  return (
    <div className="space-y-4">
      <div className="text-center">
        <h1 className="text-[18px] font-semibold">How do you want to use the platform?</h1>
        <p className="mt-1 text-[12px] text-muted-foreground">
          You can change this later. Each mode builds on the previous one.
        </p>
      </div>

      <div className="grid grid-cols-3 gap-3">
        {modes.map((m) => (
          <button
            key={m.value}
            type="button"
            onClick={() => setValue("mode", m.value)}
            className={cn(
              "relative flex flex-col rounded-xl border p-4 text-left transition-colors",
              selectedMode === m.value
                ? "border-2 border-foreground"
                : "border-border hover:border-muted-foreground",
            )}
          >
            {m.badge && (
              <span className={cn("absolute -top-2 right-3 rounded-full px-2 py-0.5 text-tiny font-semibold", m.badge.color)}>
                {m.badge.label}
              </span>
            )}
            <m.icon className="mb-2 h-5 w-5 text-muted-foreground" />
            <div className="text-[13px] font-medium">{m.title}</div>
            <div className="mt-1 text-muted text-muted-foreground">{m.subtitle}</div>
            <ul className="mt-3 space-y-1">
              {m.features.map((f) => (
                <li key={f} className="text-muted text-muted-foreground">• {f}</li>
              ))}
            </ul>
            <div className="mt-auto pt-3 text-muted text-muted-foreground">{m.stripeNeeded}</div>
          </button>
        ))}
      </div>
    </div>
  );
}
