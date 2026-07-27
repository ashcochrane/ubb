import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { ErrorInline, LoadingRows } from "@/components/shared/data-states";
import { EmptyState } from "@/components/shared/empty-state";
import { CursorPagerControls } from "@/components/shared/cursor-pager";
import { formatMicros, formatShortDate } from "@/lib/format";
import { useCustomerInvoices } from "../api/queries";

/** Cursor-paginated list of a customer's subscription invoices. */
export function SubscriptionInvoices({ customerId }: { customerId: string }) {
  const pager = useCustomerInvoices(customerId);

  if (pager.isLoading) return <LoadingRows />;
  if (pager.isError)
    return <ErrorInline error={pager.error} onRetry={pager.refetch} />;
  if (pager.items.length === 0)
    return (
      <EmptyState
        title="No invoices"
        description="This customer has no subscription invoices yet."
      />
    );

  return (
    <div className="space-y-3">
      <div className="rounded-xl bg-card ring-1 ring-foreground/10">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Invoice</TableHead>
              <TableHead>Amount paid</TableHead>
              <TableHead>Period</TableHead>
              <TableHead>Paid</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {pager.items.map((inv) => (
              <TableRow key={inv.id}>
                <TableCell className="font-mono text-xs">
                  {inv.stripe_invoice_id}
                </TableCell>
                <TableCell>
                  {formatMicros(inv.amount_paid_micros, inv.currency)}
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {formatShortDate(inv.period_start)} – {formatShortDate(inv.period_end)}
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {formatShortDate(inv.paid_at)}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <CursorPagerControls pager={pager} />
    </div>
  );
}
