import { useState } from "react";
import { ArrowLeft } from "lucide-react";

import { isNotFound } from "@/api/problem";
import { CopyButton } from "@/components/shared/copy-button";
import { DetailList, type DetailItem } from "@/components/shared/detail-list";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorCard } from "@/components/shared/error-card";
import { PageHeader } from "@/components/shared/page-header";
import { ProductGate } from "@/components/shared/product-gate";
import { StatCard } from "@/components/shared/stat-card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useHasRole } from "@/hooks/use-current-role";
import { useTenantCurrency } from "@/hooks/use-tenant-config";
import { formatDate, formatMicros } from "@/lib/format";

import { useReferrer, useReferrerEarnings } from "../api/queries";
import type { ReferrerOut } from "../api/types";
import { looseDate } from "../lib/dates";
import { AttributeReferralDialog } from "./attribute-referral-dialog";
import { ReferralsTable } from "./referrals-table";

function monoCopy(value: string) {
  return (
    <span className="inline-flex max-w-full items-center gap-1.5">
      <span className="truncate" title={value}>
        {value}
      </span>
      <CopyButton value={value} />
    </span>
  );
}

function referrerItems(referrer: ReferrerOut): DetailItem[] {
  return [
    { label: "Customer ID", value: monoCopy(referrer.customer_id), mono: true },
    { label: "Referral code", value: monoCopy(referrer.referral_code), mono: true },
    { label: "Referral link token", value: monoCopy(referrer.referral_link_token), mono: true },
    {
      label: "Status",
      value: (
        <Badge variant={referrer.is_active ? "outline" : "secondary"}>
          {referrer.is_active ? "Active" : "Inactive"}
        </Badge>
      ),
    },
    { label: "Registered", value: looseDate(referrer.created_at, formatDate) },
  ];
}

export function ReferrerDetailPage({
  customerId,
  onBack,
}: {
  customerId: string;
  onBack: () => void;
}) {
  const currency = useTenantCurrency();
  const referrer = useReferrer(customerId);
  const earnings = useReferrerEarnings(customerId);
  const [attributeOpen, setAttributeOpen] = useState(false);
  const canWrite = useHasRole("write");

  return (
    <ProductGate product="referrals">
      <div className="space-y-6">
        <Button variant="ghost" size="sm" onClick={onBack} className="-ml-2 text-text-secondary">
          <ArrowLeft className="h-3.5 w-3.5" strokeWidth={1.5} />
          All referrals
        </Button>

        {referrer.isLoading ? (
          <div className="space-y-3">
            <Skeleton className="h-8 w-64" />
            <Skeleton className="h-48 w-full" />
            <Skeleton className="h-24 w-full" />
          </div>
        ) : isNotFound(referrer.error) ? (
          <EmptyState
            title="Referrer not found"
            description="This customer isn't registered as a referrer, or the record was removed."
            action={{ label: "Back to referrals", onClick: onBack }}
          />
        ) : referrer.isError ? (
          <ErrorCard
            error={referrer.error}
            onRetry={() => void referrer.refetch()}
            title="Couldn't load this referrer"
          />
        ) : referrer.data ? (
          <>
            <PageHeader
              title="Referrer"
              description={`Customer ${referrer.data.customer_id}`}
              actions={
                <Button
                  size="sm"
                  onClick={() => setAttributeOpen(true)}
                  disabled={!canWrite}
                  title={canWrite ? undefined : "Requires the Write role"}
                >
                  Attribute a referral
                </Button>
              }
            />

            <Card>
              <CardContent>
                <DetailList items={referrerItems(referrer.data)} />
              </CardContent>
            </Card>

            {earnings.isLoading ? (
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                {Array.from({ length: 4 }).map((_, index) => (
                  <Skeleton key={index} className="h-[72px] w-full" />
                ))}
              </div>
            ) : earnings.isError ? (
              <ErrorCard
                error={earnings.error}
                onRetry={() => void earnings.refetch()}
                title="Couldn't load earnings"
              />
            ) : earnings.data ? (
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                <StatCard
                  label="Total earned"
                  value={formatMicros(earnings.data.total_earned_micros, currency)}
                />
                <StatCard
                  label="Referred spend"
                  value={formatMicros(earnings.data.total_referred_spend_micros, currency)}
                />
                <StatCard
                  label="Referrals"
                  value={earnings.data.total_referrals.toLocaleString()}
                />
                <StatCard
                  label="Active referrals"
                  value={earnings.data.active_referrals.toLocaleString()}
                />
              </div>
            ) : null}

            <ReferralsTable customerId={customerId} onAttribute={() => setAttributeOpen(true)} />

            <AttributeReferralDialog
              open={attributeOpen}
              onOpenChange={setAttributeOpen}
              defaultCode={referrer.data.referral_code}
              defaultLinkToken={referrer.data.referral_link_token}
            />
          </>
        ) : null}
      </div>
    </ProductGate>
  );
}
