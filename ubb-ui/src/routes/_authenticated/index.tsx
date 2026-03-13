import { createFileRoute } from "@tanstack/react-router";
import { StatsCards } from "@/components/dashboard/stats-cards";

export const Route = createFileRoute("/_authenticated/")({
  component: DashboardHome,
});

function DashboardHome() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
        <p className="text-muted-foreground">
          Overview of your usage-based billing platform.
        </p>
      </div>
      <StatsCards
        customerCount={0}
        totalBalance={0}
        transactionCount={0}
        revenueThisMonth={0}
      />
    </div>
  );
}
