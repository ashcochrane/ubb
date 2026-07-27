import { createFileRoute } from "@tanstack/react-router";

import { BillingPage } from "@/features/billing/components/billing-page";
import { dateRangeSearchSchema } from "@/lib/date-range";

export const Route = createFileRoute("/_app/billing/")({
  validateSearch: dateRangeSearchSchema,
  component: RouteComponent,
});

function RouteComponent() {
  const search = Route.useSearch();
  const navigate = Route.useNavigate();
  return (
    <BillingPage
      search={search}
      onSearchChange={(next) => void navigate({ search: next, replace: true })}
    />
  );
}
