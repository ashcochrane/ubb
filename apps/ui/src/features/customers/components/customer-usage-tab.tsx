import { Link } from "@tanstack/react-router";
import {
  Section,
  LoadingRows,
  ErrorInline,
} from "@/components/shared/data-states";
import { EmptyState } from "@/components/shared/empty-state";
import { StatusBadge } from "@/components/shared/status-badge";
import { CursorPagerControls } from "@/components/shared/cursor-pager";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { formatMicros, formatShortDate } from "@/lib/format";
import { useCustomerUsage } from "../api/queries";

export function CustomerUsageTab({ customerId }: { customerId: string }) {
  const usage = useCustomerUsage(customerId);

  return (
    <Section title="Usage events" description="Metered events recorded for this customer, newest first.">
      {usage.isLoading ? (
        <LoadingRows />
      ) : usage.isError ? (
        <ErrorInline error={usage.error} onRetry={usage.refetch} />
      ) : usage.items.length === 0 ? (
        <EmptyState title="No usage yet" description="Recorded usage events will appear here." />
      ) : (
        <div className="space-y-3">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Event type</TableHead>
                <TableHead>Provider</TableHead>
                <TableHead className="text-right">Provider cost</TableHead>
                <TableHead className="text-right">Billed</TableHead>
                <TableHead className="text-right">Units</TableHead>
                <TableHead>When</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {usage.items.map((e) => (
                <TableRow key={e.id}>
                  <TableCell>
                    <Link to="/usage/$eventId" params={{ eventId: e.id }} className="hover:underline">
                      {e.event_type ? <StatusBadge value={e.event_type} tone="neutral" /> : e.id.slice(0, 8)}
                    </Link>
                  </TableCell>
                  <TableCell className="text-muted-foreground">{e.provider || "—"}</TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground">
                    {e.provider_cost_micros != null ? formatMicros(e.provider_cost_micros) : "—"}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {e.billed_cost_micros != null ? formatMicros(e.billed_cost_micros) : "—"}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {e.units != null ? e.units.toLocaleString() : "—"}
                  </TableCell>
                  <TableCell className="text-muted-foreground">{formatShortDate(e.effective_at)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <CursorPagerControls pager={usage} />
        </div>
      )}
    </Section>
  );
}
