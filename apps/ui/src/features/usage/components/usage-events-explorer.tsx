import { useState } from "react";
import { Link } from "@tanstack/react-router";
import { ChevronRight, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { Section, LoadingRows, ErrorInline } from "@/components/shared/data-states";
import { EmptyState } from "@/components/shared/empty-state";
import { StatusBadge } from "@/components/shared/status-badge";
import { CursorPagerControls } from "@/components/shared/cursor-pager";
import { FormField } from "@/components/shared/form-field";
import { formatMicros, formatDate } from "@/lib/format";
import { useCustomerUsage } from "../api/queries";

interface AppliedFilters {
  customerId: string;
  tag_key?: string;
  tag_value?: string;
  past_limit?: boolean;
}

/**
 * The usage-event stream is customer-scoped, so this explorer takes a customer
 * ID (plus optional tag / past-limit filters) and lists that customer's events.
 * Each row links to the event detail page.
 */
export function UsageEventsExplorer() {
  const [customerId, setCustomerId] = useState("");
  const [tagKey, setTagKey] = useState("");
  const [tagValue, setTagValue] = useState("");
  const [pastLimit, setPastLimit] = useState(false);
  const [applied, setApplied] = useState<AppliedFilters | null>(null);

  function apply(e: React.FormEvent) {
    e.preventDefault();
    if (!customerId.trim()) return;
    setApplied({
      customerId: customerId.trim(),
      tag_key: tagKey.trim() || undefined,
      tag_value: tagValue.trim() || undefined,
      past_limit: pastLimit || undefined,
    });
  }

  return (
    <Section
      title="Usage events"
      description="Browse a customer's recorded usage events. Enter a customer ID to load their stream."
    >
      <form onSubmit={apply} className="mb-4 grid grid-cols-1 gap-3 sm:grid-cols-4">
        <FormField label="Customer ID">
          {(id) => (
            <Input
              id={id}
              value={customerId}
              onChange={(e) => setCustomerId(e.target.value)}
              placeholder="cus_…"
            />
          )}
        </FormField>
        <FormField label="Tag key" hint="optional">
          {(id) => (
            <Input id={id} value={tagKey} onChange={(e) => setTagKey(e.target.value)} />
          )}
        </FormField>
        <FormField label="Tag value" hint="optional">
          {(id) => (
            <Input id={id} value={tagValue} onChange={(e) => setTagValue(e.target.value)} />
          )}
        </FormField>
        <div className="flex items-end gap-3">
          <label className="mb-2 flex items-center gap-2 text-sm text-muted-foreground">
            <input
              type="checkbox"
              checked={pastLimit}
              onChange={(e) => setPastLimit(e.target.checked)}
              className="size-4"
            />
            Past limit
          </label>
          <Button type="submit" disabled={!customerId.trim()}>
            <Search />
            Load
          </Button>
        </div>
      </form>

      {applied ? (
        <UsageEventsList key={JSON.stringify(applied)} filters={applied} />
      ) : (
        <EmptyState
          icon={Search}
          title="No customer selected"
          description="Enter a customer ID above and press Load to see their usage events."
        />
      )}
    </Section>
  );
}

function UsageEventsList({ filters }: { filters: AppliedFilters }) {
  const pager = useCustomerUsage(filters.customerId, {
    tag_key: filters.tag_key,
    tag_value: filters.tag_value,
    past_limit: filters.past_limit,
  });

  if (pager.isLoading) return <LoadingRows rows={4} />;
  if (pager.isError) return <ErrorInline error={pager.error} onRetry={pager.refetch} />;
  if (pager.items.length === 0) {
    return (
      <EmptyState
        title="No usage events"
        description="This customer has no usage events matching the current filters."
      />
    );
  }

  return (
    <div className="space-y-3">
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Event type</TableHead>
              <TableHead>Provider</TableHead>
              <TableHead className="text-right">Provider cost</TableHead>
              <TableHead className="text-right">Billed</TableHead>
              <TableHead className="text-right">Units</TableHead>
              <TableHead>When</TableHead>
              <TableHead className="w-8" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {pager.items.map((ev) => (
              <TableRow key={ev.id}>
                <TableCell>
                  <Link
                    to="/usage/$eventId"
                    params={{ eventId: ev.id }}
                    className="hover:underline"
                  >
                    {ev.event_type ? (
                      <StatusBadge value={ev.event_type} tone="neutral" />
                    ) : (
                      <span className="text-muted-foreground">—</span>
                    )}
                  </Link>
                </TableCell>
                <TableCell>{ev.provider || <span className="text-muted-foreground">—</span>}</TableCell>
                <TableCell className="text-right font-mono text-xs">
                  {ev.provider_cost_micros != null ? formatMicros(ev.provider_cost_micros) : "—"}
                </TableCell>
                <TableCell className="text-right font-mono text-xs">
                  {ev.billed_cost_micros != null ? formatMicros(ev.billed_cost_micros) : "—"}
                </TableCell>
                <TableCell className="text-right font-mono text-xs">
                  {ev.units != null ? ev.units.toLocaleString() : "—"}
                </TableCell>
                <TableCell className="text-muted-foreground">{formatDate(ev.effective_at)}</TableCell>
                <TableCell>
                  <Link to="/usage/$eventId" params={{ eventId: ev.id }}>
                    <ChevronRight className="size-4 text-muted-foreground" />
                  </Link>
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
