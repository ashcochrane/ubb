import { createFileRoute } from "@tanstack/react-router";
import { NewCardWizard } from "@/features/pricing-cards/components/new-card-wizard";

export const Route = createFileRoute("/_app/pricing-cards/new")({
  component: NewCardWizard,
});
