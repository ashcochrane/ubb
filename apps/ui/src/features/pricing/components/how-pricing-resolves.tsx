import { Card, CardContent } from "@/components/ui/card";

const STEPS = [
  {
    title: "Assigned price book",
    body: "If a customer has a price book assigned (on their customer page), its rates set what they're billed.",
  },
  {
    title: "Provider default price book",
    body: "Otherwise the default price book for the event's provider applies.",
  },
  {
    title: "Markup over provider cost",
    body: "If no price book matches, we take what the provider charged you and add your default markup. With no markup set, customers pay exactly the provider cost.",
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
