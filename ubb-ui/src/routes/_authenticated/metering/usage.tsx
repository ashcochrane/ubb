import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/_authenticated/metering/usage")({
  component: UsageExplorerPage,
});

function UsageExplorerPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Usage Explorer</h1>
        <p className="text-muted-foreground">
          Query and visualize usage events.
        </p>
      </div>
      <div className="rounded-lg border border-dashed p-12 text-center text-muted-foreground">
        Usage event explorer coming soon.
      </div>
    </div>
  );
}
