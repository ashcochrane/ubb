import { createFileRoute } from "@tanstack/react-router";

import { EventsPage } from "@/features/events/components/events-page";
import { eventsSearchSchema } from "@/features/events/lib/search";

export const Route = createFileRoute("/_app/events/")({
  validateSearch: eventsSearchSchema,
  component: RouteComponent,
});

function RouteComponent() {
  const search = Route.useSearch();
  const navigate = Route.useNavigate();
  return (
    <EventsPage
      search={search}
      onSearchChange={(next) => void navigate({ search: next, replace: true })}
      onOpenEvent={(eventId, customerId) =>
        void navigate({
          to: "/events/$eventId",
          params: { eventId },
          search: { customer_id: customerId },
        })
      }
      onGoToCustomers={() => void navigate({ to: "/customers" })}
    />
  );
}
