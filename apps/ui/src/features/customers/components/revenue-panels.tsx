import * as React from "react";
import { toast } from "sonner";

import { problemMessage } from "@/api/problem";
import { ErrorCard } from "@/components/shared/error-card";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useHasRole } from "@/hooks/use-current-role";
import { revenueModeLabel } from "@/lib/labels";

import { useRevenueMode, useSaveRevenueMode } from "../api/queries";

const ADMIN_HINT = "Requires the Admin role.";

export function RevenuePanels({ customerId }: { customerId: string }) {
  return (
    <div className="grid gap-3">
      <RevenueModeCard customerId={customerId} />
    </div>
  );
}

// THE RECURRING REVENUE CARD WAS HERE AND IS GONE (#496, slice 7 section 9).
// It wrote one recurring amount per customer against a record with no periods
// and no source reference, over an interval nothing ever divided by, and the
// backend then added the amount into the same response field as a Stripe
// subscription - so nothing on this page could say where a revenue number had
// come from.
//
// The grid drops to ONE column rather than holding an empty half open: a card
// missing for two tickets reads as a defect, and the slot is cheaper to
// restore than to explain. The replacement panel is #508's and writes the
// tenant-supplied revenue record: one figure per period, with the span, the
// recognition method and the tenant's own source reference on it -
// and the mid-period affordance (#153 section 19f) that the retired card
// absorbed silently by prorating.

const MODE_OPTIONS = [
  {
    value: "inherit",
    label: "Inherit workspace default",
    explanation:
      "No override — meter-only workspaces resolve to metered only; billing workspaces resolve to billed.",
  },
  {
    value: "billed",
    label: "Billed",
    explanation:
      "Billed usage counts as revenue for this customer, so margin = revenue − provider cost.",
  },
  {
    value: "metered_only",
    label: "Metered only",
    explanation:
      "Usage is tracked but billed amounts do NOT count as revenue — margin shows only the cost of serving this customer (plus any subscription or recurring revenue).",
  },
];

function RevenueModeCard({ customerId }: { customerId: string }) {
  const isAdmin = useHasRole("admin");
  const query = useRevenueMode(customerId);
  const mutation = useSaveRevenueMode(customerId);
  const [selected, setSelected] = React.useState<string | null>(null);

  const stored = query.data?.revenue_mode ?? "";
  const value = selected ?? (stored === "" ? "inherit" : stored);
  const explanation = MODE_OPTIONS.find((option) => option.value === value)?.explanation;

  const save = async () => {
    try {
      await mutation.mutateAsync(value === "inherit" ? "" : value);
      setSelected(null);
      toast.success("Revenue mode saved");
    } catch {
      // surfaced below (422 invalid_revenue_mode included)
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Revenue mode</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {query.isLoading ? (
          <Skeleton className="h-32 w-full" />
        ) : query.isError ? (
          <ErrorCard error={query.error} onRetry={() => void query.refetch()} />
        ) : (
          <>
            <p className="text-[12px] text-text-secondary">
              Controls whether billed usage counts as revenue in this customer's
              margin math. Resolved right now:{" "}
              <span className="font-medium text-text-primary">
                {revenueModeLabel(query.data?.resolved)}
              </span>
              .
            </p>
            <Select value={value} onValueChange={setSelected}>
              <SelectTrigger className="w-full" aria-label="Revenue mode">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {MODE_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {explanation && <p className="text-[11px] text-text-muted">{explanation}</p>}
            {mutation.error != null && (
              <p className="text-[12px] text-danger-dark" role="alert">
                {problemMessage(mutation.error)}
              </p>
            )}
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                onClick={() => void save()}
                disabled={mutation.isPending || !isAdmin || selected === null}
              >
                {mutation.isPending ? "Working…" : "Save mode"}
              </Button>
              {!isAdmin && <span className="text-[11px] text-text-muted">{ADMIN_HINT}</span>}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
