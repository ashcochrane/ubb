import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/_authenticated/settings/general")({
  component: GeneralPage,
});

function GeneralPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">General</h1>
        <p className="text-muted-foreground">
          Tenant name, API keys, and configuration.
        </p>
      </div>
      <div className="rounded-lg border border-dashed p-12 text-center text-muted-foreground">
        General settings coming soon.
      </div>
    </div>
  );
}
