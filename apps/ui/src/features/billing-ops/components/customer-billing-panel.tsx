import { Wallet } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Section,
  ErrorInline,
  LoadingRows,
} from "@/components/shared/data-states";
import { CursorPagerControls } from "@/components/shared/cursor-pager";
import { formatMicros } from "@/lib/format";
import { useBalance, useTransactions } from "../api/queries";
import { TopUpDialog } from "./top-up-dialog";
import { WithdrawDialog } from "./withdraw-dialog";
import { AutoTopUpForm } from "./auto-top-up-form";
import { TransactionsTable } from "./transactions-table";

/**
 * Full customer wallet surface: balance, top-up/withdraw, auto top-up policy,
 * and the cursor-paginated transaction ledger. Embedded in the customer detail
 * page (the one tolerated cross-feature import).
 */
export function CustomerBillingPanel({ customerId }: { customerId: string }) {
  const balance = useBalance(customerId);
  const transactions = useTransactions(customerId);
  const currency = balance.data?.currency ?? "USD";

  return (
    <div className="space-y-6">
      <Section
        title="Wallet balance"
        actions={
          <div className="flex gap-2">
            <TopUpDialog customerId={customerId} />
            <WithdrawDialog customerId={customerId} />
          </div>
        }
      >
        {balance.isLoading ? (
          <Skeleton className="h-10 w-40" />
        ) : balance.isError ? (
          <ErrorInline error={balance.error} onRetry={() => balance.refetch()} />
        ) : balance.data ? (
          <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2">
            <div>
              <div className="text-3xl font-semibold tabular-nums">
                {formatMicros(balance.data.balance_micros, currency)}
              </div>
              <div className="mt-0.5 text-xs text-muted-foreground">Available balance</div>
            </div>
            {typeof balance.data.promo_micros === "number" && balance.data.promo_micros > 0 && (
              <Stat label="Promotional" value={formatMicros(balance.data.promo_micros, currency)} />
            )}
            {typeof balance.data.expiring_micros === "number" && balance.data.expiring_micros > 0 && (
              <Stat label="Expiring soon" value={formatMicros(balance.data.expiring_micros, currency)} />
            )}
            {balance.data.negative_since && (
              <Stat label="Negative since" value={new Date(balance.data.negative_since).toLocaleDateString()} />
            )}
          </div>
        ) : (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Wallet className="size-4" />
            No wallet yet — a top-up will create one.
          </div>
        )}
      </Section>

      <AutoTopUpForm customerId={customerId} />

      <Section title="Transaction ledger">
        {transactions.isLoading ? (
          <LoadingRows rows={4} />
        ) : transactions.isError ? (
          <ErrorInline error={transactions.error} onRetry={transactions.refetch} />
        ) : (
          <div className="space-y-3">
            <TransactionsTable rows={transactions.items} currency={currency} />
            <CursorPagerControls pager={transactions} />
          </div>
        )}
      </Section>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-sm font-medium tabular-nums">{value}</div>
      <div className="mt-0.5 text-xs text-muted-foreground">{label}</div>
    </div>
  );
}
