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
      // The page hands over which record the ledger files this book under: a
      // Pricing Book and a cost book are two records with two sets of audit
      // actions, so the filter is derived from the book rather than spelled
      // here (#368, #372).
      onShowAuditTrail={(search) =>
        void navigate({ to: "/settings/audit", search })
      }
    />
  );
}
