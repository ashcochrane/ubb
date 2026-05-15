import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useBalance, useTransactions } from "../api/queries";
import { TopUpDialog } from "./top-up-dialog";
import { WithdrawDialog } from "./withdraw-dialog";
import { AutoTopUpForm } from "./auto-top-up-form";
import { TransactionsTable } from "./transactions-table";

function microsToDollars(micros: number): string {
  return `$${(micros / 1_000_000).toFixed(2)}`;
}

export function CustomerBillingPanel({ customerId }: { customerId: string }) {
  const balance = useBalance(customerId);
  const transactions = useTransactions(customerId);

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <CardTitle className="text-base">Wallet balance</CardTitle>
          <div className="flex gap-2">
            <TopUpDialog customerId={customerId} />
            <WithdrawDialog customerId={customerId} />
          </div>
        </CardHeader>
        <CardContent>
          {balance.isLoading || !balance.data ? (
            <Skeleton className="h-10 w-40" />
          ) : (
            <div className="text-3xl font-medium">
              {microsToDollars(balance.data.balanceMicros)}
              <span className="ml-2 text-sm text-muted-foreground">
                {balance.data.currency}
              </span>
            </div>
          )}
        </CardContent>
      </Card>

      <AutoTopUpForm customerId={customerId} />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Recent transactions</CardTitle>
        </CardHeader>
        <CardContent>
          {transactions.isLoading || !transactions.data ? (
            <div className="space-y-2">
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-full" />
            </div>
          ) : (
            <TransactionsTable rows={transactions.data.data} />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
