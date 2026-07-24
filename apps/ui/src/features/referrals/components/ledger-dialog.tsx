import { EmptyState } from "@/components/shared/empty-state";
import { ErrorCard } from "@/components/shared/error-card";
import { LoadMore } from "@/components/shared/load-more";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatMicros, formatShortDate } from "@/lib/format";
import { humanize } from "@/lib/labels";

import { useReferralLedger } from "../api/queries";
import type { ReferralOut } from "../api/types";
import { looseDate } from "../lib/dates";

export function LedgerDialog({
  referral,
  onClose,
  currency,
}: {
  referral: ReferralOut | null;
  onClose: () => void;
  currency: string;
}) {
  const ledger = useReferralLedger(referral?.id ?? "", referral !== null);

  return (
    <Dialog
      open={referral !== null}
      onOpenChange={(open) => {
        if (!open) onClose();
      }}
    >
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Reward ledger</DialogTitle>
          <DialogDescription>
            {referral
              ? `Per-period reward history for ${referral.referred_external_id} — the immutable record behind the running totals, written by batch reconciliation.`
              : ""}
          </DialogDescription>
        </DialogHeader>
        {ledger.isInitialLoading ? (
          <div className="space-y-2">
            {Array.from({ length: 3 }).map((_, index) => (
              <Skeleton key={index} className="h-8 w-full" />
            ))}
          </div>
        ) : ledger.isError ? (
          <ErrorCard
            error={ledger.error}
            onRetry={() => void ledger.refetch()}
            title="Couldn't load the ledger"
          />
        ) : ledger.rows.length === 0 ? (
          <EmptyState
            title="No ledger entries yet"
            description="Entries are written when period reconciliation runs — a fresh referral won't have any."
          />
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Period</TableHead>
                  <TableHead className="text-right">Referred spend</TableHead>
                  <TableHead className="text-right">Raw cost</TableHead>
                  <TableHead className="text-right">Reward</TableHead>
                  <TableHead>Method</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {ledger.rows.map((entry) => (
                  <TableRow key={entry.id}>
                    <TableCell className="text-[12px]">
                      {looseDate(entry.period_start, formatShortDate)} –{" "}
                      {looseDate(entry.period_end, formatShortDate)}
                    </TableCell>
                    <TableCell className="text-right">
                      {formatMicros(entry.referred_spend_micros, currency)}
                    </TableCell>
                    <TableCell className="text-right">
                      {formatMicros(entry.raw_cost_micros, currency)}
                    </TableCell>
                    <TableCell className="text-right font-medium">
                      {formatMicros(entry.reward_micros, currency)}
                    </TableCell>
                    <TableCell>{humanize(entry.calculation_method)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <LoadMore
              shownCount={ledger.rows.length}
              hasMore={ledger.hasMore}
              isFetchingNextPage={ledger.isFetchingNextPage}
              onLoadMore={ledger.fetchNextPage}
              noun="entries"
            />
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
