import { createFileRoute } from "@tanstack/react-router";
import { DevelopersPage } from "@/features/developers/components/developers-page";

export const Route = createFileRoute("/_app/developers/")({
  component: DevelopersPage,
});
