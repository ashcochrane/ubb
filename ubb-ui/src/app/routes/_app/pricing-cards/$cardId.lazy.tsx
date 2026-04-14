import { createLazyFileRoute } from "@tanstack/react-router";
import { ReconciliationPage } from "@/features/reconciliation/components/reconciliation-page";

export const Route = createLazyFileRoute("/_app/pricing-cards/$cardId")({
  component: CardReconciliationRoute,
});

function CardReconciliationRoute() {
  const { cardId } = Route.useParams();
  return <ReconciliationPage cardId={cardId} />;
}
