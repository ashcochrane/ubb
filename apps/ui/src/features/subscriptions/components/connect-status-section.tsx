// Stripe Connect prerequisite: charging subscriptions requires an onboarded
// Stripe account (account connected AND charges enabled).

import { Link } from "@tanstack/react-router";
import { CircleCheck, TriangleAlert } from "lucide-react";

import { ErrorCard } from "@/components/shared/error-card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Skeleton } from "@/components/ui/skeleton";

import { useConnectStatus } from "../api/queries";
import type { ConnectStatus } from "../api/types";

export function ConnectStatusSection() {
  const query = useConnectStatus();

  if (query.isLoading) {
    return <Skeleton className="h-14 w-full" />;
  }
  if (query.isError) {
    return (
      <ErrorCard
        error={query.error}
        onRetry={() => void query.refetch()}
        title="Couldn't check the Stripe connection"
      />
    );
  }
  if (!query.data) return null;
  return <ConnectStatusAlert status={query.data} />;
}

/** Presentational branch — exported so tests can exercise both states directly. */
export function ConnectStatusAlert({ status }: { status: ConnectStatus }) {
  if (status.onboarded) {
    return (
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-lg border border-border bg-card px-3 py-2 text-sm ring-1 ring-foreground/5">
        <CircleCheck className="h-4 w-4 text-muted-foreground" strokeWidth={1.5} />
        <span className="font-medium text-foreground">Stripe connected</span>
        <span className="text-muted-foreground">
          Charges are enabled — plans you create here can be charged.
        </span>
        <span className="ml-auto max-w-full truncate font-mono text-[12px] text-muted-foreground" title={status.account_id}>
          {status.account_id}
        </span>
      </div>
    );
  }

  return (
    <Alert>
      <TriangleAlert strokeWidth={1.5} />
      <AlertTitle>Connect Stripe before charging</AlertTitle>
      <AlertDescription>
        {status.account_id === ""
          ? "No Stripe account is connected yet. "
          : "A Stripe account is connected, but it can't accept charges yet. "}
        Subscriptions are charged through your Stripe account, so plans can't bill anyone until
        onboarding is finished. Complete it in{" "}
        <Link to="/settings">Settings</Link>.
      </AlertDescription>
    </Alert>
  );
}
