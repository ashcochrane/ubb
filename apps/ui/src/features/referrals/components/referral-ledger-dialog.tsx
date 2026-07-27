import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogTrigger,
} from "@/components/ui/dialog";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { LoadingRows, ErrorInline } from "@/components/shared/data-states";
import { EmptyState } from "@/components/shared/empty-state";
import { StatusBadge } from "@/components/shared/status-badge";
import { CursorPagerControls } from "@/components/shared/cursor-pager";
import { formatMicros, formatShortDate } from "@/lib/format";
import { useAuth } from "@/features/auth/hooks/use-auth";
import { useReferralLedger } from "../api/queries";

/**
 * Per-period reward ledger for a single referral. Fetches lazily — only once
 * the dialog is opened.
 */
export function ReferralLedgerDialog({
  referralId,
  trigger,
}: {
  referralId: string;
  trigger: React.ReactNode;
}) {
  const [open, setOpen] = useState(false);
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={trigger as React.ReactElement} />
      <DialogContent className="sm:max-w-3xl">
        <DialogHeader>
          <DialogTitle>Reward ledger</DialogTitle>
          <DialogDescription>
            How this referral's reward was calculated, period by period.
          </DialogDescription>
        </DialogHeader>
        {open && <LedgerBody referralId={referralId} />}
      </DialogContent>
    </Dialog>
  );
}

function LedgerBody({ referralId }: { referralId: string }) {
  const { defaultCurrency } = useAuth();
  const pager = useReferralLedger(referralId);

  if (pager.isLoading) return <LoadingRows rows={4} />;
  if (pager.isError)
    return <ErrorInline error={pager.error} onRetry={pager.refetch} />;
  if (pager.items.length === 0)
    return (
      <EmptyState
        title="No ledger entries"
        description="Rewards are recorded here once the referred customer generates billed spend."
      />
    );

  return (
    <div className="space-y-3">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>Period</TableHead>
            <TableHead>Method</TableHead>
            <TableHead className="text-right">Referred spend</TableHead>
            <TableHead className="text-right">Raw cost</TableHead>
            <TableHead className="text-right">Reward</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {pager.items.map((entry) => (
            <TableRow key={entry.id}>
              <TableCell className="text-muted-foreground">
                {formatShortDate(entry.period_start)} –{" "}
                {formatShortDate(entry.period_end)}
              </TableCell>
              <TableCell>
                <StatusBadge value={entry.calculation_method} tone="neutral" />
              </TableCell>
              <TableCell className="text-right">
                {formatMicros(entry.referred_spend_micros, defaultCurrency)}
              </TableCell>
              <TableCell className="text-right">
                {formatMicros(entry.raw_cost_micros, defaultCurrency)}
              </TableCell>
              <TableCell className="text-right font-medium">
                {formatMicros(entry.reward_micros, defaultCurrency)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
      <CursorPagerControls pager={pager} />
    </div>
  );
}
