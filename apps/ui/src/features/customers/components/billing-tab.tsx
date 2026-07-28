import * as React from "react";
import { AlertTriangle, Info } from "lucide-react";
import { Link } from "@tanstack/react-router";

import { DisabledHint } from "@/components/shared/disabled-hint";
import { ErrorCard } from "@/components/shared/error-card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useHasRole } from "@/hooks/use-current-role";
import { useIsPostpaid } from "@/hooks/use-tenant-config";
import { formatDate, formatMicros } from "@/lib/format";
import { cn } from "@/lib/utils";

import { useBalance } from "../api/queries";
import { AdjustDialog, PreCheckDialog } from "./adjust-dialogs";
import { BillingConfigSection } from "./billing-config-section";
import { BudgetSection } from "./budget-section";
import { GrantsSection } from "./grants-section";
import { TopUpDialog, WithdrawDialog } from "./money-dialogs";
import { TransactionsSection } from "./transactions-section";
import { UsageInvoicesSection } from "./usage-invoices-section";

const ADMIN_HINT = "Requires the Admin role.";
const WRITE_HINT = "Requires the Write role.";

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
  const postpaid = useIsPostpaid();

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
              {balance.data.is_pooled_seat && (
                <p className="text-[12px] text-text-secondary">
                  This balance belongs to the billing owner,{" "}
                  <Link
                    to="/customers/$customerId"
                    params={{ customerId: balance.data.billing_owner_id }}
                    className="font-medium underline-offset-2 hover:underline"
                  >
                    {balance.data.billing_owner_external_id}
                  </Link>
                  {" "}— this seat has no wallet of its own; every spend draws
                  down the business's balance.
                </p>
              )}
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
                {!postpaid && (
                  <>
                    <DisabledHint disabled={!canWrite} hint={WRITE_HINT}>
                      <Button size="sm" onClick={() => setDialog("top-up")} disabled={!canWrite}>
                        Top up
                      </Button>
                    </DisabledHint>
                    <DisabledHint disabled={!isAdmin} hint={ADMIN_HINT}>
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={() => setDialog("withdraw")}
                        disabled={!isAdmin}
                      >
                        Withdraw
                      </Button>
                    </DisabledHint>
                  </>
                )}
                <DisabledHint disabled={!isAdmin} hint={ADMIN_HINT}>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setDialog("credit")}
                    disabled={!isAdmin}
                  >
                    Manual credit
                  </Button>
                </DisabledHint>
                <DisabledHint disabled={!isAdmin} hint={ADMIN_HINT}>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setDialog("debit")}
                    disabled={!isAdmin}
                  >
                    Manual debit
                  </Button>
                </DisabledHint>
                <DisabledHint disabled={!canWrite} hint={WRITE_HINT}>
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setDialog("pre-check")}
                    disabled={!canWrite}
                  >
                    Run access check
                  </Button>
                </DisabledHint>
              </div>
              {postpaid && (
                <Alert>
                  <Info />
                  <AlertDescription>
                    Top-up and withdraw are hidden under postpaid — usage
                    isn't drawn from a prepaid wallet here; it's invoiced
                    through Stripe at period close instead. Manual credit and
                    debit above still move the ledger directly.
                  </AlertDescription>
                </Alert>
              )}
            </>
          ) : null}
        </CardContent>
      </Card>

      <TransactionsSection customerId={customerId} />
      <GrantsSection customerId={customerId} />
      <UsageInvoicesSection customerId={customerId} />
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
