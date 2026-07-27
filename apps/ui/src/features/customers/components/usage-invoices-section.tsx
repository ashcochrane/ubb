// Per-customer usage-invoice history — the Stripe-push record for each closed
// billing period (GET /billing/customers/{id}/usage-invoices, read floor).
// Rows carry their own currency; failed pushes get the red treatment and an
// expandable last-attempt error.

import * as React from "react";
import { ChevronDown, ChevronRight, ReceiptText } from "lucide-react";

import { CopyButton } from "@/components/shared/copy-button";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorCard } from "@/components/shared/error-card";
import { LoadMore } from "@/components/shared/load-more";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatCalendarDate, formatMicros } from "@/lib/format";
import { humanize, usageInvoiceStatusLabel } from "@/lib/labels";

import { useCustomerUsageInvoices } from "../api/queries";
import type { UsageInvoiceOut } from "../api/types";

const FAILED_STATUSES = new Set(["failed", "failed_permanent"]);

export function UsageInvoicesSection({ customerId }: { customerId: string }) {
  const list = useCustomerUsageInvoices(customerId);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Usage invoices</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-[11px] text-text-muted">
          This customer's usage per billing period, pushed to Stripe as invoice
          line items when the period closes.
        </p>
        {list.isInitialLoading ? (
          <Skeleton className="h-28 w-full" />
        ) : list.isError ? (
          <ErrorCard error={list.error} onRetry={() => void list.refetch()} />
        ) : list.rows.length === 0 ? (
          <EmptyState
            icon={ReceiptText}
            title="No usage invoices yet"
            description="Rows appear after the first billing period closes and this customer's usage is pushed to Stripe."
          />
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Period</TableHead>
                  <TableHead className="text-right">Total</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Stripe invoice</TableHead>
                  <TableHead className="text-right">Push attempts</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {list.rows.map((invoice) => (
                  <UsageInvoiceRow key={invoice.period_start} invoice={invoice} />
                ))}
              </TableBody>
            </Table>
            <LoadMore
              shownCount={list.rows.length}
              hasMore={list.hasMore}
              isFetchingNextPage={list.isFetchingNextPage}
              onLoadMore={list.fetchNextPage}
              noun="invoices"
            />
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function UsageInvoiceRow({ invoice }: { invoice: UsageInvoiceOut }) {
  const [expanded, setExpanded] = React.useState(false);
  const failed = FAILED_STATUSES.has(invoice.status);
  const hasError = Boolean(invoice.last_attempt_error);

  return (
    <>
      <TableRow>
        <TableCell className="whitespace-nowrap text-[12px]">
          {formatCalendarDate(invoice.period_start)} →{" "}
          {formatCalendarDate(invoice.period_end)}
        </TableCell>
        <TableCell className="text-right tabular-nums">
          {formatMicros(invoice.total_billed_micros, invoice.currency)}
        </TableCell>
        <TableCell>
          <Badge
            variant={failed ? "destructive" : "outline"}
            title={invoice.skip_reason ? humanize(invoice.skip_reason) : undefined}
          >
            {usageInvoiceStatusLabel(invoice.status)}
          </Badge>
        </TableCell>
        <TableCell>
          {invoice.stripe_invoice_id ? (
            <span className="flex items-center gap-1.5">
              <span
                className="max-w-[160px] truncate font-mono text-[12px]"
                title={invoice.stripe_invoice_id}
              >
                {invoice.stripe_invoice_id}
              </span>
              <CopyButton
                value={invoice.stripe_invoice_id}
                label="Copy Stripe invoice ID"
              />
            </span>
          ) : (
            <span className="text-text-muted">—</span>
          )}
        </TableCell>
        <TableCell className="text-right">
          <span className="inline-flex items-center justify-end gap-1 tabular-nums">
            {invoice.push_attempts ?? 0}
            {hasError && (
              <Button
                variant="ghost"
                size="xs"
                onClick={() => setExpanded((current) => !current)}
                aria-expanded={expanded}
              >
                {expanded ? (
                  <ChevronDown className="h-3.5 w-3.5" />
                ) : (
                  <ChevronRight className="h-3.5 w-3.5" />
                )}
                Last error
              </Button>
            )}
          </span>
        </TableCell>
      </TableRow>
      {expanded && hasError && (
        <TableRow>
          <TableCell colSpan={5} className="bg-bg-subtle/50">
            <span className="block whitespace-normal font-mono text-[12px] text-danger-dark">
              {invoice.last_attempt_error}
            </span>
          </TableCell>
        </TableRow>
      )}
    </>
  );
}
