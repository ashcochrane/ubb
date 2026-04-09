import { createFileRoute } from "@tanstack/react-router";
import { PageHeader } from "@/components/shared/page-header";

export const Route = createFileRoute("/_app/export/")({
  component: ExportPage,
});

function ExportPage() {
  return (
    <div className="space-y-6">
      <PageHeader
        title="Export"
        description="Download event-level data as CSV or JSON."
      />
      <div className="rounded-lg border border-dashed p-12 text-center text-sm text-muted-foreground">
        Data Export — Phase 8
      </div>
    </div>
  );
}
