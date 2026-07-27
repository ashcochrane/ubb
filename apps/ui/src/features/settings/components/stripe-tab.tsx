import { CheckCircle2, ExternalLink } from "lucide-react";
import { useAuth } from "@/features/auth/hooks/use-auth";
import { Button } from "@/components/ui/button";
import {
  Section,
  DetailGrid,
  DetailRow,
  LoadingRows,
  ErrorInline,
} from "@/components/shared/data-states";
import { StatusBadge } from "@/components/shared/status-badge";
import { useConnectStatus, useConnectStart } from "../api/queries";
import { readConnectUrl, readString, readBool } from "../api/types";

/**
 * Stripe Connect onboarding. `/connect/status` is an untyped `object`, so we
 * probe it defensively for a handful of common status fields. Starting
 * onboarding returns a redirect url under `url` (or similar) which we navigate
 * to; the account id from tenant config tells us if we're already connected.
 */
export function StripeTab() {
  const auth = useAuth();
  const status = useConnectStatus();
  const start = useConnectStart();

  const beginOnboarding = async () => {
    const result = await start.mutateAsync(window.location.href);
    const url = readConnectUrl(result);
    if (url) {
      window.location.assign(url);
    }
  };

  return (
    <Section
      title="Stripe Connect"
      description="Connect a Stripe account so UBB can push invoices and collect payments on your behalf."
      actions={
        !auth.stripeConnected && (
          <Button size="sm" onClick={beginOnboarding} disabled={start.isPending}>
            {start.isPending ? "Redirecting…" : "Connect Stripe"}
          </Button>
        )
      }
    >
      {auth.stripeConnected ? (
        <div className="flex items-center gap-2 rounded-lg border border-border px-3 py-2.5 text-sm">
          <CheckCircle2 className="size-4 text-foreground" />
          <span className="font-medium">Stripe account connected</span>
          {auth.tenant?.stripe_connected_account_id && (
            <span className="font-mono text-xs text-muted-foreground">
              {auth.tenant.stripe_connected_account_id}
            </span>
          )}
        </div>
      ) : (
        <p className="mb-4 flex items-center gap-1.5 text-sm text-muted-foreground">
          <ExternalLink className="size-3.5" />
          You'll be redirected to Stripe to finish onboarding, then returned here.
        </p>
      )}

      <div className="mt-4">
        {status.isLoading ? (
          <LoadingRows rows={2} />
        ) : status.isError ? (
          <ErrorInline error={status.error} onRetry={() => status.refetch()} title="Couldn't load Stripe status" />
        ) : status.data ? (
          <StatusDetails data={status.data} />
        ) : null}
      </div>
    </Section>
  );
}

function StatusDetails({ data }: { data: Record<string, unknown> }) {
  const accountId = readString(data, "account_id") ?? readString(data, "stripe_account_id");
  const chargesEnabled = readBool(data, "charges_enabled");
  const payoutsEnabled = readBool(data, "payouts_enabled");
  const detailsSubmitted = readBool(data, "details_submitted");
  const statusText = readString(data, "status");

  const anyKnown =
    accountId !== null ||
    chargesEnabled !== null ||
    payoutsEnabled !== null ||
    detailsSubmitted !== null ||
    statusText !== null;

  if (!anyKnown) {
    return (
      <p className="text-sm text-muted-foreground">
        Connection status was not returned in a recognised shape.
      </p>
    );
  }

  return (
    <DetailGrid>
      {accountId !== null && (
        <DetailRow label="Account ID">
          <span className="font-mono text-xs break-all">{accountId}</span>
        </DetailRow>
      )}
      {statusText !== null && (
        <DetailRow label="Status">
          <StatusBadge value={statusText} />
        </DetailRow>
      )}
      {chargesEnabled !== null && (
        <DetailRow label="Charges enabled">
          <StatusBadge value={chargesEnabled ? "Enabled" : "Disabled"} tone={chargesEnabled ? "solid" : "muted"} />
        </DetailRow>
      )}
      {payoutsEnabled !== null && (
        <DetailRow label="Payouts enabled">
          <StatusBadge value={payoutsEnabled ? "Enabled" : "Disabled"} tone={payoutsEnabled ? "solid" : "muted"} />
        </DetailRow>
      )}
      {detailsSubmitted !== null && (
        <DetailRow label="Details submitted">
          <StatusBadge value={detailsSubmitted ? "Yes" : "No"} tone={detailsSubmitted ? "solid" : "muted"} />
        </DetailRow>
      )}
    </DetailGrid>
  );
}
