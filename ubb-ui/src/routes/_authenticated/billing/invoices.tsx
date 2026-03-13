import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/_authenticated/billing/invoices")({
  component: InvoicesPage,
});

function InvoicesPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Invoices</h1>
        <p className="text-muted-foreground">
          Invoice list with status and detail views.
        </p>
      </div>
      <div className="rounded-lg border border-dashed p-12 text-center text-muted-foreground">
        Invoice management coming soon.
      </div>
    </div>
  );
}
