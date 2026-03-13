import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/_authenticated/metering/analytics")({
  component: AnalyticsPage,
});

function AnalyticsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Analytics</h1>
        <p className="text-muted-foreground">
          Revenue breakdowns and usage trends.
        </p>
      </div>
      <div className="rounded-lg border border-dashed p-12 text-center text-muted-foreground">
        Analytics dashboards coming soon.
      </div>
    </div>
  );
}
