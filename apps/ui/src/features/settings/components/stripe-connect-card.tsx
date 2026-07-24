import { X } from "lucide-react";

import { problemMessage } from "@/api/problem";
import { CopyButton } from "@/components/shared/copy-button";
import { ErrorCard } from "@/components/shared/error-card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

import { useConnectStatus, useStartConnect } from "../api/queries";

export function StripeConnectCard({
  isAdmin,
  connectedParam,
  onClearConnected,
}: {
  isAdmin: boolean;
  connectedParam?: string;
  onClearConnected?: () => void;
}) {
  // Safe to poll: the GET lazily re-polls Stripe while charges aren't
  // enabled yet. Poll only right after the OAuth return (stops when onboarded).
  const status = useConnectStatus({ poll: connectedParam === "true" });
  const start = useStartConnect();

  const data = status.data;
  const onboarded = data?.onboarded === true;

  const connect = () => {
    start.mutate(window.location.href, {
      onSuccess: ({ authorize_url }) => {
        if (authorize_url) window.location.assign(authorize_url);
      },
    });
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Stripe</CardTitle>
        <CardDescription>
          Prepaid top-ups, postpaid invoices, and subscriptions charge
          customers through your connected Stripe account.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {connectedParam !== undefined && (
          <Alert
            variant={connectedParam === "true" ? "default" : "destructive"}
          >
            <AlertTitle className="flex items-center justify-between gap-2">
              {connectedParam === "true"
                ? "Stripe connection completed"
                : "Stripe connection didn't complete"}
              {onClearConnected && (
                <button
                  type="button"
                  aria-label="Dismiss"
                  onClick={onClearConnected}
                  className="text-muted-foreground hover:text-foreground"
                >
                  <X className="h-3.5 w-3.5" />
                </button>
              )}
            </AlertTitle>
            <AlertDescription>
              {connectedParam === "true"
                ? onboarded
                  ? "Your Stripe account is connected and charges are enabled."
                  : "Waiting for Stripe to finish its account checks — this page re-checks automatically."
                : "The connection was canceled or failed on Stripe's side. You can retry below."}
            </AlertDescription>
          </Alert>
        )}

        {status.isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-5 w-64" />
            <Skeleton className="h-5 w-40" />
          </div>
        ) : status.isError ? (
          <ErrorCard
            error={status.error}
            onRetry={() => void status.refetch()}
            title="Couldn't load the Stripe connection status"
          />
        ) : data ? (
          <div className="space-y-3">
            <div className="flex items-center justify-between gap-4">
              <p className="text-sm font-medium">Account</p>
              {data.account_id ? (
                <span className="flex items-center gap-1.5 font-mono text-[12px]">
                  {data.account_id}
                  <CopyButton value={data.account_id} />
                </span>
              ) : (
                <span className="text-sm text-muted-foreground">
                  Not connected
                </span>
              )}
            </div>
            <div className="flex items-center justify-between gap-4">
              <p className="text-sm font-medium">Status</p>
              <Badge variant={onboarded ? "secondary" : "outline"}>
                {onboarded
                  ? "Ready to charge customers"
                  : data.account_id
                    ? "Onboarding incomplete — charges not enabled yet"
                    : "Not connected"}
              </Badge>
            </div>
          </div>
        ) : null}

        {start.isError && (
          <p className="text-xs text-destructive">
            {problemMessage(start.error)}
          </p>
        )}

        <div className="flex items-center justify-end gap-3">
          {!isAdmin && (
            <span className="text-[12px] text-muted-foreground">
              Requires the Admin role.
            </span>
          )}
          <Button
            size="sm"
            variant={onboarded ? "outline" : "default"}
            onClick={connect}
            disabled={!isAdmin || start.isPending}
          >
            {start.isPending
              ? "Redirecting…"
              : onboarded
                ? "Reconnect Stripe"
                : "Connect Stripe"}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
