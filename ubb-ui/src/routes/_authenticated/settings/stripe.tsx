import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/_authenticated/settings/stripe")({
  component: StripePage,
});

function StripePage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Stripe</h1>
        <p className="text-muted-foreground">
          Stripe connection status and account linking.
        </p>
      </div>
      <div className="rounded-lg border border-dashed p-12 text-center text-muted-foreground">
        Stripe integration settings coming soon.
      </div>
    </div>
  );
}
