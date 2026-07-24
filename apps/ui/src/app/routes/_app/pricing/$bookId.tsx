import { createFileRoute } from "@tanstack/react-router";
import { BookDetailPage } from "@/features/pricing/components/book-detail-page";

export const Route = createFileRoute("/_app/pricing/$bookId")({
  component: RouteComponent,
});

function RouteComponent() {
  const { bookId } = Route.useParams();
  return <BookDetailPage bookId={bookId} />;
}
