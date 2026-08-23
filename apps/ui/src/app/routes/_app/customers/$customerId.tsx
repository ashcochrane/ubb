import { createFileRoute } from "@tanstack/react-router";
import { z } from "zod";

import { CustomerDetailPage } from "@/features/customers/components/customer-detail-page";
import { CustomerPricingTab } from "@/features/pricing/components/customer-pricing-tab";
import { dateRangeSearchSchema } from "@/lib/date-range";

// Unknown ?tab= values coerce to undefined → the Overview tab, never a blank panel.
const detailSearchSchema = dateRangeSearchSchema.extend({
  tab: z
    .enum(["overview", "usage", "pricing", "billing", "subscription"])
    .optional()
    .catch(undefined),
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
      // ⚠ THE ROUTE IS WHERE THE TWO FEATURES MEET (#372). A customer's own
      // pricing rules are the pricing feature's surface and the customer page
      // is the customers feature's; the console's dependency rule forbids
      // either from importing the other's components, and the route is the
      // layer that may see both.
      pricingTab={<CustomerPricingTab customerId={customerId} />}
    />
  );
}
