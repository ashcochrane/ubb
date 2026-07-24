import { ErrorCard } from "@/components/shared/error-card";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

import { useConnectStatus } from "../api/queries";
import type { TenantConfig } from "../api/types";

/** What some products need before they can actually do their job. */
export function PrerequisitesCard({ config }: { config: TenantConfig }) {
  const needsStripe =
    config.billing_mode === "prepaid" ||
    config.billing_mode === "postpaid" ||
    config.products.includes("subscriptions");
  const status = useConnectStatus({ enabled: needsStripe });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Prerequisites</CardTitle>
        <CardDescription>
          Things some products need before they can charge or ingest.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {needsStripe && (
          <div className="flex items-start justify-between gap-4">
            <div>
              <p className="text-sm font-medium">Stripe account</p>
              <p className="max-w-md text-[13px] text-muted-foreground">
                Prepaid top-ups, postpaid invoicing, and subscriptions all
                charge through your connected Stripe account.{" "}
                <a href="/settings" className="underline">
                  Manage it in Workspace settings
                </a>
                .
              </p>
            </div>
            {status.isLoading ? (
              <Skeleton className="h-5 w-28" />
            ) : status.isError ? (
              <Badge variant="outline">Status unavailable</Badge>
            ) : status.data?.onboarded ? (
              <Badge variant="secondary">Connected</Badge>
            ) : status.data?.account_id ? (
              <Badge variant="outline">Charges not enabled yet</Badge>
            ) : (
              <Badge variant="destructive">Not connected</Badge>
            )}
          </div>
        )}
        {status.isError && (
          <ErrorCard
            error={status.error}
            onRetry={() => void status.refetch()}
            title="Couldn't load the Stripe connection status"
          />
        )}

        <div className="flex items-start justify-between gap-4">
          <div>
            <p className="text-sm font-medium">Async ingestion scope</p>
            <p className="max-w-md text-[13px] text-muted-foreground">
              The Async ingestion product only gates the high-throughput
              ingest endpoint (<span className="font-mono text-[12px]">POST /usage/ingest</span>).
              Standard usage recording works for every workspace with
              Metering.
            </p>
          </div>
          <Badge variant={config.products.includes("metering_async") ? "secondary" : "outline"}>
            {config.products.includes("metering_async") ? "Enabled" : "Disabled"}
          </Badge>
        </div>
      </CardContent>
    </Card>
  );
}
