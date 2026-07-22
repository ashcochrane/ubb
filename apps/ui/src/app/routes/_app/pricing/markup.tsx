import { createFileRoute } from "@tanstack/react-router";
import { MarkupPage } from "@/features/pricing/components/markup-page";

export const Route = createFileRoute("/_app/pricing/markup")({
  component: MarkupPage,
});
