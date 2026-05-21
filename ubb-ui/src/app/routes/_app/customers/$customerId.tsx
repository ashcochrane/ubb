import { createFileRoute } from "@tanstack/react-router";
import { CustomerDetailPage } from "@/features/customers/components/customer-detail-page";

export const Route = createFileRoute("/_app/customers/$customerId")({
  component: RouteComponent,
});

function RouteComponent() {
  const { customerId } = Route.useParams();
  return <CustomerDetailPage customerId={customerId} />;
}
