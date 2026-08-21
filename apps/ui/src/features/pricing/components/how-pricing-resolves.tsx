import { Card, CardContent } from "@/components/ui/card";

const STEPS = [
  {
    title: "The customer's own rules",
    body: "If a customer has a pricing book of their own, its rules set what they're billed.",
  },
  {
    title: "The book their plan prices from",
    body: "Otherwise the book named by the customer's plan applies, and then your workspace default book.",
  },
  {
    title: "Markup over provider cost",
    body: "If no rule matches, we take what the provider charged you and add the default markup you have declared. With no markup declared, the price is unknown — nobody has said what to charge, and no amount is billed.",
  },
] as const;

/** Compact plain-language explainer: how a usage event's billed price is chosen. */
export function HowPricingResolves() {
  return (
    <Card size="sm">
      <CardContent>
        <p className="mb-3 text-[13px] font-medium text-text-primary">
          How pricing resolves
        </p>
        <ol className="flex flex-col gap-3 sm:flex-row sm:gap-6">
          {STEPS.map((step, index) => (
            <li key={step.title} className="flex min-w-0 flex-1 gap-2.5">
              <span
                aria-hidden="true"
                className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-bg-subtle text-[11px] font-semibold text-text-secondary"
              >
                {index + 1}
              </span>
              <div className="min-w-0">
                <p className="text-[13px] font-medium text-text-primary">{step.title}</p>
                <p className="mt-0.5 text-[12px] leading-relaxed text-text-secondary">
                  {step.body}
                </p>
              </div>
            </li>
          ))}
        </ol>
      </CardContent>
    </Card>
  );
}
