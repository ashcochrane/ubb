import type { ReactNode } from "react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  ErrorInline,
  LoadingRows,
} from "@/components/shared/data-states";
import { EmptyState } from "@/components/shared/empty-state";
import { StatusBadge } from "@/components/shared/status-badge";
import { CursorPagerControls } from "@/components/shared/cursor-pager";
import { formatMicros, formatShortDate, truncateId } from "@/lib/format";
import type { CursorPager } from "@/lib/use-cursor-list";
import {
  useBillingPeriods,
  useTenantInvoices,
  useTenantUsageInvoices,
} from "../api/queries";

/** Monospace, truncated technical id — blank falls back to an em-dash. */
function Mono({ value }: { value?: string | null }) {
  if (!value) return <span className="text-muted-foreground">—</span>;
  return <span className="font-mono text-xs">{truncateId(value)}</span>;
}

/** Loading / error / empty / table+pager wrapper for a cursor-paged list. */
function ListShell<T>({
  pager,
  emptyTitle,
  emptyDescription,
  columns,
  renderRow,
}: {
  pager: CursorPager<T>;
  emptyTitle: string;
  emptyDescription: string;
  columns: string[];
  renderRow: (item: T, index: number) => ReactNode;
}) {
  if (pager.isLoading) return <LoadingRows rows={6} />;
  if (pager.isError)
    return <ErrorInline error={pager.error} onRetry={pager.refetch} />;
  if (pager.items.length === 0)
    return <EmptyState title={emptyTitle} description={emptyDescription} />;

  return (
    <div className="space-y-3">
      <div className="overflow-x-auto rounded-lg border border-border">
        <Table>
          <TableHeader>
            <TableRow>
              {columns.map((c) => (
                <TableHead key={c}>{c}</TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>{pager.items.map(renderRow)}</TableBody>
        </Table>
      </div>
      <CursorPagerControls pager={pager} />
    </div>
  );
}

export function UsageInvoicesList({ period }: { period?: string }) {
  const pager = useTenantUsageInvoices(period);
  return (
    <ListShell
      pager={pager}
      emptyTitle="No usage invoices"
      emptyDescription="No customer usage invoices for this filter yet."
      columns={[
        "Customer",
        "Period start",
        "Billed",
        "Status",
        "Stripe invoice",
        "Attempts",
        "Notes",
      ]}
      renderRow={(inv, i) => (
        <TableRow key={`${inv.external_id}-${i}`}>
          <TableCell>
            <div className="flex flex-col">
              <span>{inv.external_id || "—"}</span>
              <Mono value={inv.customer_id} />
            </div>
          </TableCell>
          <TableCell>{formatShortDate(inv.period_start)}</TableCell>
          <TableCell className="tabular-nums">
            {formatMicros(inv.total_billed_micros)}
          </TableCell>
          <TableCell>
            <StatusBadge value={inv.status} />
          </TableCell>
          <TableCell>
            <Mono value={inv.stripe_invoice_id} />
          </TableCell>
          <TableCell className="tabular-nums">
            {inv.push_attempts ?? 0}
          </TableCell>
          <TableCell className="max-w-[16rem]">
            {inv.skip_reason ? (
              <span className="text-xs text-muted-foreground">
                Skipped: {inv.skip_reason}
              </span>
            ) : inv.last_attempt_error ? (
              <span className="text-xs text-destructive">
                {inv.last_attempt_error}
              </span>
            ) : (
              <span className="text-muted-foreground">—</span>
            )}
          </TableCell>
        </TableRow>
      )}
    />
  );
}

export function TenantInvoicesList() {
  const pager = useTenantInvoices();
  return (
    <ListShell
      pager={pager}
      emptyTitle="No tenant invoices"
      emptyDescription="Platform-fee invoices will appear here once periods close."
      columns={["Invoice", "Billing period", "Stripe invoice", "Amount", "Status", "Created"]}
      renderRow={(inv) => (
        <TableRow key={inv.id}>
          <TableCell>
            <Mono value={inv.id} />
          </TableCell>
          <TableCell>
            <Mono value={inv.billing_period_id} />
          </TableCell>
          <TableCell>
            <Mono value={inv.stripe_invoice_id} />
          </TableCell>
          <TableCell className="tabular-nums">
            {formatMicros(inv.total_amount_micros)}
          </TableCell>
          <TableCell>
            <StatusBadge value={inv.status} />
          </TableCell>
          <TableCell>{formatShortDate(inv.created_at)}</TableCell>
        </TableRow>
      )}
    />
  );
}

export function BillingPeriodsList() {
  const pager = useBillingPeriods();
  return (
    <ListShell
      pager={pager}
      emptyTitle="No billing periods"
      emptyDescription="Billing periods will appear here as usage accrues."
      columns={["Period", "Status", "Usage cost", "Platform fee", "Events"]}
      renderRow={(p) => (
        <TableRow key={p.id}>
          <TableCell>
            {formatShortDate(p.period_start)} – {formatShortDate(p.period_end)}
          </TableCell>
          <TableCell>
            <StatusBadge value={p.status} />
          </TableCell>
          <TableCell className="tabular-nums">
            {formatMicros(p.total_usage_cost_micros)}
          </TableCell>
          <TableCell className="tabular-nums">
            {formatMicros(p.platform_fee_micros)}
          </TableCell>
          <TableCell className="tabular-nums">
            {p.event_count.toLocaleString()}
          </TableCell>
        </TableRow>
      )}
    />
  );
}
