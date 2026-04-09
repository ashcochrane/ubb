import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/shared/page-header";

export const Route = createFileRoute("/_app/")({
  component: DashboardPage,
});

function DashboardPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Dashboard"
        description="Overview of your usage-based billing platform."
      />
      <div className="rounded-lg border border-dashed p-12 text-center text-sm text-muted-foreground">
        Dashboard — Phase 3
      </div>
    </div>
  );
}
