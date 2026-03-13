import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/_authenticated/billing/top-ups")({
  component: TopUpsPage,
});

function TopUpsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Top-Ups</h1>
        <p className="text-muted-foreground">
          Auto top-up configurations and attempt history.
        </p>
      </div>
      <div className="rounded-lg border border-dashed p-12 text-center text-muted-foreground">
        Top-up management coming soon.
      </div>
    </div>
  );
}
