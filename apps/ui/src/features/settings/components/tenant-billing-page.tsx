import { FileText, Receipt } from "lucide-react";

import { CopyButton } from "@/components/shared/copy-button";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorCard } from "@/components/shared/error-card";
import { LoadMore } from "@/components/shared/load-more";
import { Badge } from "@/components/ui/badge";
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
import { useTenantCurrency } from "@/hooks/use-tenant-config";
import {
  formatCalendarDate,
  formatEventCount,
  formatMicros,
  formatShortDate,
} from "@/lib/format";
import {
  billingPeriodStatusLabel,
  tenantInvoiceStatusLabel,
} from "@/lib/labels";

import { useBillingPeriods, useTenantInvoices } from "../api/queries";

/** What UBB charges THIS workspace — platform fees, not customer invoices. */
export function TenantBillingPage() {
  const currency = useTenantCurrency();
  const periods = useBillingPeriods();
  const invoices = useTenantInvoices();

  return (
    <div className="max-w-4xl space-y-6">
      <p className="max-w-2xl text-[13px] text-muted-foreground">
        This page shows what UBB charges your workspace — the platform fee on
        your metered usage. It is not what your customers owe you; customer
        invoices live with each customer.
      </p>

      <Card>
        <CardHeader>
          <CardTitle>Billing periods</CardTitle>
          <CardDescription>
            Your workspace's monthly usage and the platform fee UBB charges
            for it.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {periods.isInitialLoading ? (
            <TableSkeleton />
          ) : periods.isError ? (
            <ErrorCard
              error={periods.error}
              onRetry={() => void periods.refetch()}
            />
          ) : periods.rows.length === 0 ? (
            <EmptyState
              icon={Receipt}
              title="No billing periods yet"
              description="Your first period appears once usage starts flowing."
            />
          ) : (
            <>
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Period</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead className="text-right">Usage cost</TableHead>
                      <TableHead className="text-right">Events</TableHead>
                      <TableHead className="text-right">Platform fee</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {periods.rows.map((period) => (
                      <TableRow key={period.id}>
                        <TableCell className="font-medium">
                          {/* Calendar dates (format: date) — render in UTC so the day never shifts. */}
                          {formatCalendarDate(period.period_start)} –{" "}
                          {formatCalendarDate(period.period_end)}
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant={
                              period.status === "open" ? "secondary" : "outline"
                            }
                          >
                            {billingPeriodStatusLabel(period.status)}
                          </Badge>
                        </TableCell>
                        <TableCell className="text-right">
                          {formatMicros(period.total_usage_cost_micros, currency)}
                        </TableCell>
                        <TableCell className="text-right">
                          {formatEventCount(period.event_count)}
                        </TableCell>
                        <TableCell className="text-right font-medium">
                          {formatMicros(period.platform_fee_micros, currency)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
              <LoadMore
                shownCount={periods.rows.length}
                hasMore={periods.hasMore}
                isFetchingNextPage={periods.isFetchingNextPage}
                onLoadMore={periods.fetchNextPage}
                noun="periods"
              />
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Invoices from UBB</CardTitle>
          <CardDescription>
            The platform-fee invoices UBB issues to your workspace via Stripe.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {invoices.isInitialLoading ? (
            <TableSkeleton />
          ) : invoices.isError ? (
            <ErrorCard
              error={invoices.error}
              onRetry={() => void invoices.refetch()}
            />
          ) : invoices.rows.length === 0 ? (
            <EmptyState
              icon={FileText}
              title="No invoices yet"
              description="UBB issues an invoice when a billing period closes."
            />
          ) : (
            <>
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead className="text-right">Total</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Stripe invoice</TableHead>
                      <TableHead>Created</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {invoices.rows.map((invoice) => (
                      <TableRow key={invoice.id}>
                        <TableCell className="text-right font-medium">
                          {formatMicros(invoice.total_amount_micros, currency)}
                        </TableCell>
                        <TableCell>
                          <Badge variant="outline">
                            {tenantInvoiceStatusLabel(invoice.status)}
                          </Badge>
                        </TableCell>
                        <TableCell>
                          {invoice.stripe_invoice_id ? (
                            <span className="flex items-center gap-1.5 font-mono text-[12px]">
                              {invoice.stripe_invoice_id}
                              <CopyButton value={invoice.stripe_invoice_id} />
                            </span>
                          ) : (
                            <span className="text-muted-foreground">—</span>
                          )}
                        </TableCell>
                        <TableCell className="text-muted-foreground">
                          {formatShortDate(invoice.created_at)}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
              <LoadMore
                shownCount={invoices.rows.length}
                hasMore={invoices.hasMore}
                isFetchingNextPage={invoices.isFetchingNextPage}
                onLoadMore={invoices.fetchNextPage}
                noun="invoices"
              />
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function TableSkeleton() {
  return (
    <div className="space-y-2">
      <Skeleton className="h-9 w-full" />
      <Skeleton className="h-9 w-full" />
      <Skeleton className="h-9 w-full" />
    </div>
  );
}
