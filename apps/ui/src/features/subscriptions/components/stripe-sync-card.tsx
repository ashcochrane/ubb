// Stripe sync: POST /subscriptions/sync — a synchronous pull of subscription
// state from Stripe into UBB's mirror, answering with {synced, skipped, errors}.

import { RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { useHasRole } from "@/hooks/use-current-role";

import { useTriggerSync } from "../api/queries";

export function StripeSyncCard() {
  const canWrite = useHasRole("write");
  const mutation = useTriggerSync();
  const result = mutation.data;

  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle>Sync with Stripe</CardTitle>
        <CardDescription>
          Pulls the latest subscription state from Stripe into UBB. Changes made through UBB stay
          in sync on their own — run this after changing subscriptions, prices, or seats directly
          in the Stripe dashboard, or whenever the mirror looks stale. It runs immediately and
          reports what it touched.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-3">
        <div className="flex items-center gap-3">
          <Button
            variant="outline"
            onClick={() => mutation.mutate()}
            disabled={mutation.isPending || !canWrite}
          >
            <RefreshCw className="h-3.5 w-3.5" strokeWidth={1.5} />
            {mutation.isPending ? "Working…" : "Sync now"}
          </Button>
          {!canWrite && (
            <p className="text-xs text-muted-foreground">Syncing requires the Write role.</p>
          )}
        </div>

        {result && (
          <div className="rounded-lg border border-border bg-muted/40 p-3">
            <div className="flex flex-wrap gap-x-8 gap-y-2">
              <div>
                <div className="text-lg font-semibold tabular-nums text-foreground">
                  {result.synced}
                </div>
                <div className="text-xs text-muted-foreground">Synced</div>
              </div>
              <div>
                <div className="text-lg font-semibold tabular-nums text-foreground">
                  {result.skipped}
                </div>
                <div className="text-xs text-muted-foreground">Skipped</div>
              </div>
              <div>
                <div className="text-lg font-semibold tabular-nums text-foreground">
                  {result.errors}
                </div>
                <div className="text-xs text-muted-foreground">Errors</div>
              </div>
            </div>
            <p className="mt-2 text-xs text-muted-foreground">
              {result.errors > 0
                ? "Some subscriptions failed to sync. Run it again — if errors persist, check the affected subscriptions in Stripe."
                : "The mirror is up to date with Stripe."}
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
