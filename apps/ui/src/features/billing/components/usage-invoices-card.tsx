// The tenant-wide usage-invoice sweep (GET /billing/usage-invoices): one row
// per customer per billing period, on the one usage-invoice shape every route
// shares since R10 Stage C5 (F-15) — period, currency, push status, where the
// Stripe invoice stands as a receivable (`payment_status`, null while not yet
// collectible), and the hosted invoice where one exists — plus the two push
// internals only the tenant's routes carry (`push_attempts`,
// `last_attempt_error`).

import { useState } from "react";
import { AlertTriangle, ExternalLink } from "lucide-react";

import { CopyButton } from "@/components/shared/copy-button";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorCard } from "@/components/shared/error-card";
import { LoadMore } from "@/components/shared/load-more";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import {
  paymentStatusWording,
  skipReasonLabel,
  usageInvoiceStatusLabel,
} from "@/lib/usage-invoice";
import { formatCalendarDate, formatDate, formatMicros } from "@/lib/format";

import { useTenantUsageInvoices } from "../api/queries";
import type { TenantUsageInvoice } from "../api/types";
import { monthToPeriodDate } from "../lib/billing-forms";
import { SectionCard } from "./section-card";

const FAILED_STATUSES = new Set(["failed", "failed_permanent"]);

export function UsageInvoicesCard() {
  const [month, setMonth] = useState("");
  const period = monthToPeriodDate(month);
  const list = useTenantUsageInvoices(period);

  return (
    <SectionCard
      title="Customer usage invoices"
      description="One row per customer per billing period — their usage, pushed to Stripe as invoice line items when the period closes."
      actions={
        <div className="flex items-center gap-2">
          <Input
            type="month"
            value={month}
            onChange={(e) => setMonth(e.target.value)}
            aria-label="Filter by billing period"
            className="h-8 w-[150px] text-[12px]"
          />
          {month && (
            <Button variant="ghost" size="sm" onClick={() => setMonth("")}>
              Clear
            </Button>
          )}
        </div>
      }
    >
      {list.isInitialLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
          <Skeleton className="h-8 w-full" />
        </div>
      ) : list.isError ? (
        <ErrorCard error={list.error} onRetry={() => void list.refetch()} />
      ) : list.rows.length === 0 ? (
        <EmptyState
          title={period ? "No usage invoices for this period" : "No usage invoices yet"}
          description={
            period
              ? "No customer had usage pushed for the selected month."
              : "Rows appear after the first billing period closes and usage is pushed to Stripe."
          }
          action={period ? { label: "Clear filter", onClick: () => setMonth("") } : undefined}
        />
      ) : (
        <TooltipProvider>
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Customer</TableHead>
                  <TableHead>Period</TableHead>
                  <TableHead className="text-right">Total</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Payment</TableHead>
                  <TableHead>Stripe invoice</TableHead>
                  <TableHead className="text-right">Push attempts</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {list.rows.map((invoice) => (
                  <InvoiceRow key={invoice.id} invoice={invoice} />
                ))}
              </TableBody>
            </Table>
          </div>
          <LoadMore
            shownCount={list.rows.length}
            hasMore={list.hasMore}
            isFetchingNextPage={list.isFetchingNextPage}
            onLoadMore={list.fetchNextPage}
            noun="invoices"
          />
        </TooltipProvider>
      )}
    </SectionCard>
  );
}

function InvoiceRow({ invoice }: { invoice: TenantUsageInvoice }) {
  const failed = FAILED_STATUSES.has(invoice.status);
  return (
    <TableRow>
      <TableCell>
        <span
          className="block max-w-[180px] truncate font-mono text-[12px]"
          title={invoice.external_id}
        >
          {invoice.external_id}
        </span>
      </TableCell>
      <TableCell className="whitespace-nowrap text-[12px] text-text-secondary">
        {/* The period's two dates are calendar dates ("YYYY-MM-DD") — formatted
            in UTC so the period never shifts a day for viewers west of
            Greenwich. */}
        {formatCalendarDate(invoice.period_start)} →{" "}
        {formatCalendarDate(invoice.period_end)}
      </TableCell>
      <TableCell className="whitespace-nowrap text-right font-medium">
        {/* The row carries its own currency: a Stripe invoice is issued in one. */}
        {formatMicros(invoice.total_billed_micros, invoice.currency)}
      </TableCell>
      <TableCell>
        <Badge
          variant={failed ? "destructive" : invoice.status === "pushed" ? "secondary" : "outline"}
          title={invoice.skip_reason ? skipReasonLabel(invoice.skip_reason) : undefined}
        >
          {usageInvoiceStatusLabel(invoice.status)}
        </Badge>
      </TableCell>
      <TableCell className="whitespace-nowrap text-[12px]" data-payment-status={invoice.payment_status ?? ""}>
        {paymentStatusWording(invoice.payment_status)}
        {invoice.paid_at && (
          <span className="ml-1.5 text-[11px] text-text-muted">
            {formatDate(invoice.paid_at)}
          </span>
        )}
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
            <CopyButton value={invoice.stripe_invoice_id} label="Copy Stripe invoice id" />
            {invoice.hosted_invoice_url && (
              <a
                href={invoice.hosted_invoice_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-0.5 text-[12px] underline-offset-2 hover:underline"
                aria-label="Open the hosted Stripe invoice"
              >
                View
                <ExternalLink className="h-3 w-3" strokeWidth={1.75} />
              </a>
            )}
          </span>
        ) : (
          <span className="text-text-muted">—</span>
        )}
      </TableCell>
      <TableCell className="text-right">
        <span className="inline-flex items-center justify-end gap-1.5">
          {invoice.push_attempts}
          {invoice.last_attempt_error && (
            <Tooltip>
              <TooltipTrigger
                aria-label="Show last push error"
                className="inline-flex items-center text-destructive"
              >
                <AlertTriangle className="h-3.5 w-3.5" strokeWidth={1.75} />
              </TooltipTrigger>
              <TooltipContent className="max-w-xs">
                {invoice.last_attempt_error}
              </TooltipContent>
            </Tooltip>
          )}
        </span>
      </TableCell>
    </TableRow>
  );
}
