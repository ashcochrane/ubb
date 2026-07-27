import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DetailGrid, DetailRow, Section } from "@/components/shared/data-states";
import { useSyncSubscriptions } from "../api/queries";

/** Trigger a full reconcile of subscription state from Stripe. */
export function SyncSection() {
  const sync = useSyncSubscriptions();

  const action = (
    <Button size="sm" onClick={() => sync.mutate()} disabled={sync.isPending}>
      <RefreshCw className={sync.isPending ? "animate-spin" : undefined} />
      {sync.isPending ? "Syncing…" : "Sync now"}
    </Button>
  );

  return (
    <Section
      title="Sync from Stripe"
      description="Pull the latest subscription and invoice state from Stripe into UBB."
      actions={action}
    >
      {sync.data ? (
        <DetailGrid>
          <DetailRow label="Synced">{sync.data.synced}</DetailRow>
          <DetailRow label="Skipped">{sync.data.skipped}</DetailRow>
          <DetailRow label="Errors">{sync.data.errors}</DetailRow>
        </DetailGrid>
      ) : (
        <p className="text-sm text-muted-foreground">
          Run a sync to reconcile subscriptions and invoices. Counts appear here when it finishes.
        </p>
      )}
    </Section>
  );
}
