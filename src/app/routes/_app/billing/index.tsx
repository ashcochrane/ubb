import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/shared/page-header";

export const Route = createFileRoute("/_app/billing/")({
  component: BillingPage,
});

function BillingPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Billing"
        description="Margin management and balance configuration."
      />
      <div className="rounded-lg border border-dashed p-12 text-center text-sm text-muted-foreground">
        Margin Management — Phase 7
      </div>
    </div>
  );
}
