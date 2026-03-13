import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/_authenticated/billing/wallets")({
  component: WalletsPage,
});

function WalletsPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold tracking-tight">Wallets</h1>
        <p className="text-muted-foreground">
          Customer wallet balances and low-balance alerts.
        </p>
      </div>
      <div className="rounded-lg border border-dashed p-12 text-center text-muted-foreground">
        Wallet management coming soon.
      </div>
    </div>
  );
}
