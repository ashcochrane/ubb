import { createFileRoute } from "@tanstack/react-router";

import { CustomersPage } from "@/features/customers/components/customers-page";
import { dateRangeSearchSchema } from "@/lib/date-range";

export const Route = createFileRoute("/_app/customers/")({
  validateSearch: dateRangeSearchSchema,
  component: RouteComponent,
});

function RouteComponent() {
  const search = Route.useSearch();
  const navigate = Route.useNavigate();
  return (
    <CustomersPage
      search={search}
      onSearchChange={(next) => void navigate({ search: next, replace: true })}
      onOpenCustomer={(customerId) =>
        void navigate({ to: "/customers/$customerId", params: { customerId } })
      }
    />
  );
}
