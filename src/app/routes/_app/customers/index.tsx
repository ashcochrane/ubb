import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/shared/page-header";

export const Route = createFileRoute("/_app/customers/")({
  component: CustomersPage,
});

function CustomersPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Customers"
        description="Manage Stripe-to-SDK customer mappings."
      />
      <div className="rounded-lg border border-dashed p-12 text-center text-sm text-muted-foreground">
        Customer Mapping — Phase 5
      </div>
    </div>
  );
}
