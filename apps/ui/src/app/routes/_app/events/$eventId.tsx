import { createFileRoute } from "@tanstack/react-router";

import { EventDetailPage } from "@/features/events/components/event-detail-page";
import { eventDetailSearchSchema } from "@/features/events/lib/search";

export const Route = createFileRoute("/_app/events/$eventId")({
  validateSearch: eventDetailSearchSchema,
  component: RouteComponent,
});

function RouteComponent() {
  const { eventId } = Route.useParams();
  const { customer_id } = Route.useSearch();
  const navigate = Route.useNavigate();
  return (
    <EventDetailPage
      eventId={eventId}
      customerId={customer_id}
      onBack={() =>
        void navigate({
          to: "/events",
          search: customer_id !== undefined ? { customer_id } : {},
        })
      }
    />
  );
}
