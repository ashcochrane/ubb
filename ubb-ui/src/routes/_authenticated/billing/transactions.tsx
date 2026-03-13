import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/_authenticated/billing/transactions")({
  component: TransactionsPage,
});

function TransactionsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Transactions</h1>
        <p className="text-muted-foreground">Filterable transaction log.</p>
      </div>
      <div className="rounded-lg border border-dashed p-12 text-center text-muted-foreground">
        Transaction log coming soon.
      </div>
    </div>
  );
}
