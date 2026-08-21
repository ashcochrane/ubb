// Pricing overrides for one customer: markup (the GET returns the RESOLVED
// value — inherited vs overridden is indistinguishable, and the copy says so)
// and price-book assignment (write-only: no endpoint reads the current
// assignment back).

import * as React from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { toast } from "sonner";

import { problemMessage } from "@/api/problem";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { ErrorCard } from "@/components/shared/error-card";
import { FormField } from "@/components/shared/form-field";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useHasRole } from "@/hooks/use-current-role";
import { useTenantCurrency } from "@/hooks/use-tenant-config";
import { formatMicros, formatPercentMicros } from "@/lib/format";

import {
  useCustomerMarkup,
  useRemoveMarkup,
  useSaveMarkup,
} from "../api/queries";
import { microsToUnits, toMicros } from "../lib/helpers";
import { markupSchema, percentToMicros, type MarkupForm } from "../lib/schemas";

const ADMIN_HINT = "Requires the Admin role.";

export function PricingTab({ customerId }: { customerId: string }) {
  return (
    <div className="grid gap-3 lg:grid-cols-2">
      <MarkupCard customerId={customerId} />
    </div>
  );
}

function MarkupCard({ customerId }: { customerId: string }) {
  const currency = useTenantCurrency();
  const isAdmin = useHasRole("admin");
  const query = useCustomerMarkup(customerId);
  const save = useSaveMarkup(customerId);
  const remove = useRemoveMarkup(customerId);
  const [removeOpen, setRemoveOpen] = React.useState(false);

  const form = useForm<MarkupForm>({
    resolver: zodResolver(markupSchema),
    defaultValues: { percent: "", uplift: "" },
  });

  const resolved = query.data;
  React.useEffect(() => {
    if (resolved) {
      form.reset({
        percent: String(resolved.markup_percentage_micros / 1_000_000),
        uplift: microsToUnits(resolved.fixed_uplift_micros),
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [resolved]);

  const submit = form.handleSubmit(async (values) => {
    try {
      await save.mutateAsync({
        markup_percentage_micros: percentToMicros(values.percent),
        fixed_uplift_micros: toMicros(values.uplift || "0"),
      });
      toast.success("Markup override set for this customer");
    } catch {
      // surfaced below
    }
  });

  const confirmRemove = async () => {
    try {
      const result = await remove.mutateAsync();
      setRemoveOpen(false);
      toast.success(
        result.status === "no_override"
          ? "No override existed — this customer was already inheriting the workspace default."
          : "Override removed — this customer now inherits the workspace default.",
      );
    } catch (error) {
      setRemoveOpen(false);
      toast.error(problemMessage(error));
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Markup</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {query.isLoading ? (
          <Skeleton className="h-36 w-full" />
        ) : query.isError ? (
          <ErrorCard error={query.error} onRetry={() => void query.refetch()} />
        ) : resolved ? (
          <>
            <div>
              <div className="text-label text-text-muted">Resolved markup</div>
              <div className="text-[20px] font-semibold tracking-tight">
                {formatPercentMicros(resolved.markup_percentage_micros)}
                {resolved.fixed_uplift_micros > 0 && (
                  <span className="text-[13px] font-normal text-text-secondary">
                    {" "}
                    + {formatMicros(resolved.fixed_uplift_micros, currency)} per event
                  </span>
                )}
              </div>
              <p className="mt-1 text-[11px] text-text-muted">
                This is the value pricing resolves for this customer right now.
                The API can't tell you whether it comes from a customer override
                or the workspace default — the read is always resolved.
              </p>
            </div>
            <form onSubmit={(event) => void submit(event)} className="space-y-2.5">
              <div className="grid grid-cols-2 gap-2.5">
                <FormField
                  label="Markup %"
                  error={form.formState.errors.percent?.message}
                  hint="Applied on top of provider cost."
                >
                  {(id) => (
                    <Input id={id} inputMode="decimal" {...form.register("percent")} />
                  )}
                </FormField>
                <FormField
                  label={`Fixed uplift (${currency.toUpperCase()})`}
                  error={form.formState.errors.uplift?.message}
                  hint="Flat amount added per event."
                >
                  {(id) => (
                    <Input id={id} inputMode="decimal" {...form.register("uplift")} />
                  )}
                </FormField>
              </div>
              <p className="text-[11px] text-text-muted">
                Setting an override — even 0% + 0 — SHADOWS the workspace default
                and pins this customer at cost. To go back to inheriting, use
                "Remove override" instead of saving zeros.
              </p>
              {save.error != null && (
                <p className="text-[12px] text-danger-dark" role="alert">
                  {problemMessage(save.error)}
                </p>
              )}
              <div className="flex flex-wrap items-center gap-2">
                <Button type="submit" size="sm" disabled={save.isPending || !isAdmin}>
                  {save.isPending ? "Working…" : "Set override"}
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => setRemoveOpen(true)}
                  disabled={remove.isPending || !isAdmin}
                >
                  Remove override — inherit default
                </Button>
                {!isAdmin && (
                  <span className="text-[11px] text-text-muted">{ADMIN_HINT}</span>
                )}
              </div>
            </form>
          </>
        ) : null}
      </CardContent>
      <ConfirmDialog
        open={removeOpen}
        onOpenChange={setRemoveOpen}
        title="Remove markup override?"
        description="This customer will revert to inheriting the workspace default markup. If no override exists, nothing changes."
        confirmLabel="Remove override"
        onConfirm={() => void confirmRemove()}
        pending={remove.isPending}
      />
    </Card>
  );
}

// ⚠ `PriceBookCard` IS DELETED (#368). It picked a price book from a list and
// assigned it to this customer; the record that held that assignment is gone,
// with its route. A customer reaches a book through their PLAN — which is
// where their pricing already resolved from, and which the plans feature
// already edits — or through a book that carries them, declared as an
// override. There is no third way to reach one, so there is nothing here to
// choose between.
