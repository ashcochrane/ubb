import { createFileRoute } from "@tanstack/react-router";
import { PricingPage } from "@/features/pricing/components/pricing-page";

export const Route = createFileRoute("/_app/pricing/")({
  component: RouteComponent,
});

function RouteComponent() {
  const navigate = Route.useNavigate();
  return (
    <PricingPage
      onOpenBook={(bookId) =>
        void navigate({ to: "/pricing/$bookId", params: { bookId } })
      }
    />
  );
}
