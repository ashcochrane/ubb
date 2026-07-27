import { createFileRoute } from "@tanstack/react-router";
import { BookDetailPage } from "@/features/pricing/components/book-detail-page";

export const Route = createFileRoute("/_app/pricing/$bookId")({
  component: RouteComponent,
});

function RouteComponent() {
  const { bookId } = Route.useParams();
  const navigate = Route.useNavigate();
  return (
    <BookDetailPage
      bookId={bookId}
      onBackToPricing={() => void navigate({ to: "/pricing" })}
      onShowAuditTrail={() =>
        void navigate({
          to: "/settings/audit",
          search: { resource_type: "rate_card", resource_id: bookId },
        })
      }
    />
  );
}
