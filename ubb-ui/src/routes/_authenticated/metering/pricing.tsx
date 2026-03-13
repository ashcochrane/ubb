import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/_authenticated/metering/pricing")({
  component: PricingPage,
});

function PricingPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Pricing</h1>
        <p className="text-muted-foreground">
          Manage provider rates and markups.
        </p>
      </div>
      <div className="rounded-lg border border-dashed p-12 text-center text-muted-foreground">
        Rate cards and markup management coming soon.
      </div>
    </div>
  );
}
