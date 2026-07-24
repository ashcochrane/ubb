import * as React from "react";
import { AlertTriangle } from "lucide-react";

import { ErrorCard } from "@/components/shared/error-card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useHasRole } from "@/hooks/use-current-role";
import { formatDate, formatMicros } from "@/lib/format";
import { cn } from "@/lib/utils";

import { useBalance } from "../api/queries";
import { AdjustDialog, PreCheckDialog } from "./adjust-dialogs";
import { BillingConfigSection } from "./billing-config-section";
import { BudgetSection } from "./budget-section";
import { GrantsSection } from "./grants-section";
import { TopUpDialog, WithdrawDialog } from "./money-dialogs";
import { TransactionsSection } from "./transactions-section";

type DialogKind = "top-up" | "withdraw" | "credit" | "debit" | "pre-check" | null;

export function BillingTab({
  customerId,
  externalId,
}: {
  customerId: string;
  externalId: string;
}) {
  const balance = useBalance(customerId);
  const [dialog, setDialog] = React.useState<DialogKind>(null);
  const canWrite = useHasRole("write");
  const isAdmin = useHasRole("admin");
  const adminTitle = isAdmin ? undefined : "Requires the Admin role";

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Balance</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {balance.isLoading ? (
            <Skeleton className="h-20 w-full" />
          ) : balance.isError ? (
            <ErrorCard error={balance.error} onRetry={() => void balance.refetch()} />
          ) : balance.data ? (
            <>
              <div className="flex flex-wrap items-end gap-x-8 gap-y-2">
                <div>
                  <div className="text-label text-text-muted">Total spendable</div>
                  <div
                    className={cn(
                      "text-[26px] font-bold tracking-[-0.6px]",
                      balance.data.balance_micros < 0 && "text-danger-dark",
                    )}
                  >
                    {formatMicros(balance.data.balance_micros, balance.data.currency)}
                  </div>
                </div>
                <div>
                  <div className="text-label text-text-muted">Promo credit</div>
                  <div className="text-[15px] font-semibold">
                    {formatMicros(balance.data.promo_micros ?? 0, balance.data.currency)}
                  </div>
                </div>
                <div>
                  <div className="text-label text-text-muted">Expiring</div>
                  <div className="text-[15px] font-semibold">
                    {formatMicros(
                      balance.data.expiring_micros ?? 0,
                      balance.data.currency,
                    )}
                    {balance.data.next_expiry_at && (
                      <span className="ml-1.5 text-[11px] font-normal text-text-muted">
                        next expiry {formatDate(balance.data.next_expiry_at)}
                      </span>
                    )}
                  </div>
                </div>
              </div>
              {balance.data.negative_since && (
                <Alert variant="destructive">
                  <AlertTriangle />
                  <AlertTitle>Balance has been negative since {formatDate(balance.data.negative_since)}</AlertTitle>
                  <AlertDescription>
                    Nothing acts on this automatically — it's visibility so you can
                    decide whether to top up, debit, or stop serving.
                  </AlertDescription>
                </Alert>
              )}
              <div className="flex flex-wrap items-center gap-2">
                <Button size="sm" onClick={() => setDialog("top-up")} disabled={!canWrite}>
                  Top up
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setDialog("withdraw")}
                  disabled={!isAdmin}
                  title={adminTitle}
                >
                  Withdraw
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setDialog("credit")}
                  disabled={!isAdmin}
                  title={adminTitle}
                >
                  Manual credit
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setDialog("debit")}
                  disabled={!isAdmin}
                  title={adminTitle}
                >
                  Manual debit
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => setDialog("pre-check")}
                  disabled={!canWrite}
                >
                  Run access check
                </Button>
              </div>
            </>
          ) : null}
        </CardContent>
      </Card>

      <TransactionsSection customerId={customerId} />
      <GrantsSection customerId={customerId} />
      <BudgetSection customerId={customerId} />
      <BillingConfigSection customerId={customerId} />

      <TopUpDialog
        customerId={customerId}
        open={dialog === "top-up"}
        onOpenChange={(open) => setDialog(open ? "top-up" : null)}
      />
      <WithdrawDialog
        customerId={customerId}
        balance={balance.data}
        open={dialog === "withdraw"}
        onOpenChange={(open) => setDialog(open ? "withdraw" : null)}
      />
      <AdjustDialog
        direction="credit"
        externalId={externalId}
        open={dialog === "credit"}
        onOpenChange={(open) => setDialog(open ? "credit" : null)}
      />
      <AdjustDialog
        direction="debit"
        externalId={externalId}
        open={dialog === "debit"}
        onOpenChange={(open) => setDialog(open ? "debit" : null)}
      />
      <PreCheckDialog
        customerId={customerId}
        open={dialog === "pre-check"}
        onOpenChange={(open) => setDialog(open ? "pre-check" : null)}
      />
    </div>
  );
}
