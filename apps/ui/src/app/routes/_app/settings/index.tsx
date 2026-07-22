import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/shared/page-header";

export const Route = createFileRoute("/_app/settings/")({
  component: SettingsPage,
});

function SettingsPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Settings"
        description="Stripe connection, API keys, and account configuration."
      />
      <div className="rounded-lg border border-dashed p-12 text-center text-sm text-muted-foreground">
        Settings — coming soon
      </div>
    </div>
  );
}
