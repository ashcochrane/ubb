import { useState } from "react";
import { AlertTriangle } from "lucide-react";

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
import { useTenantCurrency } from "@/hooks/use-tenant-config";
import { humanize, usageInvoiceStatusLabel } from "@/lib/labels";
import { formatMicros, formatShortDate } from "@/lib/format";

import { useTenantUsageInvoices } from "../api/queries";
import type { TenantUsageInvoice } from "../api/types";
import { monthToPeriodDate } from "../lib/billing-forms";
import { SectionCard } from "./section-card";

const FAILED_STATUSES = new Set(["failed", "failed_permanent"]);

export function UsageInvoicesCard() {
  const [month, setMonth] = useState("");
  const period = monthToPeriodDate(month);
  const currency = useTenantCurrency();
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
                  <TableHead>Stripe invoice</TableHead>
                  <TableHead className="text-right">Push attempts</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {list.rows.map((invoice) => (
                  <InvoiceRow
                    key={`${invoice.customer_id}-${invoice.period_start}`}
                    invoice={invoice}
                    currency={currency}
                  />
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

function InvoiceRow({
  invoice,
  currency,
}: {
  invoice: TenantUsageInvoice;
  currency: string;
}) {
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
        {formatShortDate(invoice.period_start)}
      </TableCell>
      <TableCell className="whitespace-nowrap text-right font-medium">
        {formatMicros(invoice.total_billed_micros, currency)}
      </TableCell>
      <TableCell>
        <Badge
          variant={failed ? "destructive" : invoice.status === "pushed" ? "secondary" : "outline"}
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
            <CopyButton value={invoice.stripe_invoice_id} label="Copy Stripe invoice id" />
          </span>
        ) : (
          <span className="text-text-muted">—</span>
        )}
      </TableCell>
      <TableCell className="text-right">
        <span className="inline-flex items-center justify-end gap-1.5">
          {invoice.push_attempts ?? 0}
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
