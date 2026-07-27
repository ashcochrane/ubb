// The ledger's customer scope: pick a customer (labelled by shortened UUID —
// the margin list carries no external ids), then show the resolved
// external_id from the customer margin detail.

import { CopyButton } from "@/components/shared/copy-button";
import { ErrorCard } from "@/components/shared/error-card";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { problemMessage } from "@/api/problem";

import { useCustomerMargin, useMarginCustomers } from "../api/queries";
import { shortId } from "../lib/search";

const NONE = "none";

export function CustomerScopeCard({
  customerId,
  onSelect,
  onGoToCustomers,
}: {
  customerId?: string;
  onSelect: (customerId: string | undefined) => void;
  onGoToCustomers?: () => void;
}) {
  const customers = useMarginCustomers();
  const selected = useCustomerMargin(customerId);

  if (customers.isError) {
    return (
      <ErrorCard
        error={customers.error}
        onRetry={() => void customers.refetch()}
        title="Couldn't load customers"
      />
    );
  }

  const rows = customers.data?.customers ?? [];

  return (
    <div className="rounded-md border border-border bg-bg-surface p-4">
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-[13px] font-medium text-text-primary">
          Customer
        </span>
        {customers.isLoading ? (
          <Skeleton className="h-8 w-[200px]" />
        ) : rows.length === 0 ? (
          <div className="flex items-center gap-3">
            <span className="text-[12px] text-text-secondary">
              No customers in this workspace yet.
            </span>
            {onGoToCustomers && (
              <Button variant="outline" size="sm" onClick={onGoToCustomers}>
                Go to customers
              </Button>
            )}
          </div>
        ) : (
          <Select
            value={customerId ?? NONE}
            onValueChange={(value) =>
              onSelect(
                typeof value === "string" && value !== NONE ? value : undefined,
              )
            }
          >
            <SelectTrigger
              className="h-8 w-[200px] text-[12px]"
              aria-label="Select customer"
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE}>Select a customer…</SelectItem>
              {rows.map((row) => (
                <SelectItem key={row.customer_id} value={row.customer_id}>
                  <span className="font-mono text-[12px]">
                    {shortId(row.customer_id)}
                  </span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}

        {customerId !== undefined &&
          (selected.isLoading ? (
            <Skeleton className="h-5 w-32" />
          ) : selected.isError ? (
            <span className="text-[12px] text-red-text">
              {problemMessage(selected.error)}
            </span>
          ) : selected.data ? (
            <span className="inline-flex items-center gap-1.5 text-[12px] text-text-secondary">
              resolves to{" "}
              <span className="font-mono text-[12px] font-medium text-text-primary">
                {selected.data.external_id}
              </span>
              <CopyButton value={customerId} label="Copy customer ID" />
            </span>
          ) : null)}

        {customerId !== undefined && (
          <Button variant="ghost" size="sm" onClick={() => onSelect(undefined)}>
            Clear
          </Button>
        )}
      </div>
      <p className="mt-2 text-[11px] text-text-muted">
        The ledger below is scoped to one customer at a time. The totals and
        chart above cover{" "}
        {customerId !== undefined ? "the selected customer" : "all customers"}.
      </p>
    </div>
  );
}
