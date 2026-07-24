import { createFileRoute } from "@tanstack/react-router";
import { z } from "zod";

import { CustomerDetailPage } from "@/features/customers/components/customer-detail-page";
import { dateRangeSearchSchema } from "@/lib/date-range";

const detailSearchSchema = dateRangeSearchSchema.extend({
  tab: z.string().optional().catch(undefined),
});

export const Route = createFileRoute("/_app/customers/$customerId")({
  validateSearch: detailSearchSchema,
  component: RouteComponent,
});

function RouteComponent() {
  const { customerId } = Route.useParams();
  const search = Route.useSearch();
  const navigate = Route.useNavigate();
  return (
    <CustomerDetailPage
      customerId={customerId}
      search={search}
      onSearchChange={(next) => void navigate({ search: next, replace: true })}
    />
  );
}
