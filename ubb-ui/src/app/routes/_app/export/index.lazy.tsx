import { createLazyFileRoute } from "@tanstack/react-router";
import { ExportPage } from "@/features/export/components/export-page";

export const Route = createLazyFileRoute("/_app/export/")({
  component: ExportPage,
});
