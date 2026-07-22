import { createLazyFileRoute } from "@tanstack/react-router";
import { CardDetailPage } from "@/features/pricing-cards/components/card-detail-page";

export const Route = createLazyFileRoute("/_app/pricing-cards/$cardId")({
  component: CardDetailRoute,
});

function CardDetailRoute() {
  const { cardId } = Route.useParams();
  return <CardDetailPage cardId={cardId} />;
}
