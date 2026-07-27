import { createFileRoute } from "@tanstack/react-router";
import { MarginPage } from "@/features/margin/components/margin-page";

export const Route = createFileRoute("/_app/margin/")({
  component: MarginPage,
});
