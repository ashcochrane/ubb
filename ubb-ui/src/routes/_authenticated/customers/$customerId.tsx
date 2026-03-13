import { createFileRoute, Link } from "@tanstack/react-router";
import { useCustomer } from "@/api/hooks/use-customers";
import { CustomerDetail } from "@/components/customers/customer-detail";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ArrowLeft } from "lucide-react";

export const Route = createFileRoute("/_authenticated/customers/$customerId")({
  component: CustomerDetailPage,
});

function CustomerDetailPage() {
  const { customerId } = Route.useParams();
  const { data: customer, isLoading, error } = useCustomer(customerId);

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-8 w-48" />
        <div className="grid gap-6 md:grid-cols-2">
          <Skeleton className="h-64" />
          <Skeleton className="h-64" />
        </div>
      </div>
    );
  }

  if (error || !customer) {
    return (
      <div className="space-y-4">
        <p className="text-destructive">
          Failed to load customer. The customer may not exist or there was a
          network error.
        </p>
        <Button variant="outline" render={<Link to="/customers" />}>
          <ArrowLeft className="size-4" />
          Back to Customers
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="icon" render={<Link to="/customers" />}>
          <ArrowLeft className="size-4" />
        </Button>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">
            {customer.external_id}
          </h1>
          <p className="text-muted-foreground">Customer details</p>
        </div>
      </div>
      <CustomerDetail customer={customer} />
    </div>
  );
}
