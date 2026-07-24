import { useState } from "react";

import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorCard } from "@/components/shared/error-card";
import { LoadMore } from "@/components/shared/load-more";
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
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useHasRole } from "@/hooks/use-current-role";
import { useTenantCurrency } from "@/hooks/use-tenant-config";
import { formatMicros, formatShortDate } from "@/lib/format";
import { humanize, rewardTypeLabel } from "@/lib/labels";
import { toastSuccess } from "@/lib/mutations";

import { useReferrerReferrals, useRevokeReferral } from "../api/queries";
import type { ReferralOut } from "../api/types";
import { looseDate } from "../lib/dates";
import { LedgerDialog } from "./ledger-dialog";

export function ReferralsTable({
  customerId,
  onAttribute,
}: {
  customerId: string;
  /** Opens the attribute-a-referral dialog (owned by the page). */
  onAttribute: () => void;
}) {
  const currency = useTenantCurrency();
  const referrals = useReferrerReferrals(customerId);
  const revokeMutation = useRevokeReferral();
  const canWrite = useHasRole("write");

  const [toRevoke, setToRevoke] = useState<ReferralOut | null>(null);
  const [ledgerFor, setLedgerFor] = useState<ReferralOut | null>(null);

  return (
    <Card>
      <CardHeader className="border-b">
        <CardTitle>Referrals</CardTitle>
        <CardDescription>
          Customers attributed to this referrer. Each referral keeps the program settings it was
          attributed under.
        </CardDescription>
      </CardHeader>
      <CardContent className="px-0">
        {referrals.isInitialLoading ? (
          <div className="space-y-2 px-4">
            {Array.from({ length: 3 }).map((_, index) => (
              <Skeleton key={index} className="h-8 w-full" />
            ))}
          </div>
        ) : referrals.isError ? (
          <ErrorCard
            error={referrals.error}
            onRetry={() => void referrals.refetch()}
            title="Couldn't load referrals"
            className="mx-4"
          />
        ) : referrals.rows.length === 0 ? (
          <EmptyState
            title="No referrals attributed yet"
            description="Share the referrer's code or link — or attribute a referral manually."
            action={{ label: "Attribute a referral", onClick: onAttribute }}
            className="mx-4"
          />
        ) : (
          <>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Referred customer</TableHead>
                  <TableHead>Code used</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Reward</TableHead>
                  <TableHead className="text-right">Earned</TableHead>
                  <TableHead className="text-right">Referred spend</TableHead>
                  <TableHead>Attributed</TableHead>
                  <TableHead>Rewards until</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {referrals.rows.map((referral) => (
                  <TableRow key={referral.id}>
                    <TableCell title={referral.referred_customer_id}>
                      {referral.referred_external_id}
                    </TableCell>
                    <TableCell className="font-mono text-[12px]">
                      {referral.referral_code_used}
                    </TableCell>
                    <TableCell>
                      <Badge variant={referral.status === "active" ? "outline" : "secondary"}>
                        {humanize(referral.status)}
                      </Badge>
                    </TableCell>
                    <TableCell>{rewardTypeLabel(referral.reward_type)}</TableCell>
                    <TableCell className="text-right">
                      {formatMicros(referral.total_earned_micros, currency)}
                    </TableCell>
                    <TableCell className="text-right">
                      {formatMicros(referral.total_referred_spend_micros, currency)}
                    </TableCell>
                    <TableCell className="text-text-secondary">
                      {looseDate(referral.attributed_at, formatShortDate)}
                    </TableCell>
                    <TableCell className="text-text-secondary">
                      {referral.reward_window_ends_at === null
                        ? "No end"
                        : looseDate(referral.reward_window_ends_at, formatShortDate)}
                    </TableCell>
                    <TableCell className="text-right">
                      <div className="flex justify-end gap-1">
                        <Button variant="ghost" size="xs" onClick={() => setLedgerFor(referral)}>
                          Ledger
                        </Button>
                        <Button
                          variant="ghost"
                          size="xs"
                          className="text-destructive"
                          disabled={!canWrite || referral.status === "revoked"}
                          title={
                            !canWrite
                              ? "Requires the Write role"
                              : referral.status === "revoked"
                                ? "Already revoked"
                                : undefined
                          }
                          onClick={() => setToRevoke(referral)}
                        >
                          Revoke
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <LoadMore
              shownCount={referrals.rows.length}
              hasMore={referrals.hasMore}
              isFetchingNextPage={referrals.isFetchingNextPage}
              onLoadMore={referrals.fetchNextPage}
              noun="referrals"
            />
          </>
        )}
      </CardContent>

      <ConfirmDialog
        open={toRevoke !== null}
        onOpenChange={(open) => {
          if (!open) setToRevoke(null);
        }}
        title="Revoke this referral?"
        description={`Reward accrual for ${toRevoke?.referred_external_id ?? "this customer"} stops permanently and the referral is marked revoked. Amounts already earned stay on record.`}
        confirmLabel="Revoke referral"
        destructive
        pending={revokeMutation.isPending}
        onConfirm={() => {
          if (!toRevoke) return;
          revokeMutation.mutate(toRevoke.id, {
            onSuccess: () => {
              toastSuccess("Referral revoked");
              setToRevoke(null);
            },
          });
        }}
      />

      <LedgerDialog referral={ledgerFor} onClose={() => setLedgerFor(null)} currency={currency} />
    </Card>
  );
}
