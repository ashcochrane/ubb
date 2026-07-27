import * as React from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";

import { problemMessage } from "@/api/problem";
import { DisabledHint } from "@/components/shared/disabled-hint";
import { ErrorCard } from "@/components/shared/error-card";
import { FormField } from "@/components/shared/form-field";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { useHasRole } from "@/hooks/use-current-role";
import { useTenantCurrency } from "@/hooks/use-tenant-config";
import { formatMicros, formatPercentMicros } from "@/lib/format";
import { toastSuccess } from "@/lib/mutations";
import { useTenantMarkup, useUpdateTenantMarkup } from "../api/queries";
import { markupFormSchema, type MarkupFormValues } from "../lib/schemas";
import { microsToUnitString, toMicros } from "../lib/pricing-math";

/** The tenant's default markup: display card + admin edit dialog. */
export function TenantMarkupCard() {
  const markup = useTenantMarkup();
  const currency = useTenantCurrency();
  const isAdmin = useHasRole("admin");
  const [editOpen, setEditOpen] = React.useState(false);

  if (markup.isLoading) {
    return (
      <Card size="sm">
        <CardContent className="space-y-2">
          <Skeleton className="h-4 w-40" />
          <Skeleton className="h-7 w-56" />
          <Skeleton className="h-3 w-72" />
        </CardContent>
      </Card>
    );
  }
  if (markup.isError) {
    return (
      <ErrorCard
        error={markup.error}
        onRetry={() => void markup.refetch()}
        title="Couldn't load the default markup"
      />
    );
  }
  if (!markup.data) return null;

  const { markup_percentage_micros, fixed_uplift_micros } = markup.data;
  const hasMarkup = markup_percentage_micros > 0 || fixed_uplift_micros > 0;

  return (
    <Card size="sm">
      <CardContent className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-[13px] font-medium text-text-primary">Default markup</p>
          <p className="mt-1 text-xl font-semibold tracking-tight text-text-primary">
            {formatPercentMicros(markup_percentage_micros)}
            {fixed_uplift_micros > 0 && (
              <span className="text-base font-medium text-text-secondary">
                {" "}
                + {formatMicros(fixed_uplift_micros, currency)} per event
              </span>
            )}
          </p>
          <p className="mt-1 max-w-md text-[12px] leading-relaxed text-text-secondary">
            {hasMarkup
              ? "Added on top of provider cost whenever no price book covers an event."
              : "No markup configured — events without a price book are billed at exactly the provider cost."}
          </p>
        </div>
        <DisabledHint disabled={!isAdmin} hint="Requires the Admin role.">
          <Button
            variant="outline"
            size="sm"
            onClick={() => setEditOpen(true)}
            disabled={!isAdmin}
          >
            Edit
          </Button>
        </DisabledHint>
        {!isAdmin && (
          <p className="w-full text-[11px] text-text-muted">
            Changing the markup requires the Admin role.
          </p>
        )}
      </CardContent>
      <EditMarkupDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        currency={currency}
        initial={{
          percent: microsToUnitString(markup_percentage_micros),
          fixed: microsToUnitString(fixed_uplift_micros),
        }}
      />
    </Card>
  );
}

function EditMarkupDialog({
  open,
  onOpenChange,
  currency,
  initial,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  currency: string;
  initial: MarkupFormValues;
}) {
  const update = useUpdateTenantMarkup();
  const form = useForm<MarkupFormValues>({
    resolver: zodResolver(markupFormSchema),
    defaultValues: initial,
  });

  // Re-seed the form whenever the dialog opens on fresh data.
  React.useEffect(() => {
    if (open) {
      form.reset(initial);
      update.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const onSubmit = (values: MarkupFormValues) => {
    update.mutate(
      {
        markup_percentage_micros: toMicros(values.percent),
        fixed_uplift_micros: toMicros(values.fixed),
      },
      {
        onSuccess: () => {
          toastSuccess("Default markup updated");
          onOpenChange(false);
        },
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Edit default markup</DialogTitle>
          <DialogDescription>
            Applied on top of what providers charge you, for any event no price
            book covers. Existing events are never repriced.
          </DialogDescription>
        </DialogHeader>
        <form
          onSubmit={(event) => void form.handleSubmit(onSubmit)(event)}
          className="space-y-4"
        >
          <FormField
            label="Percentage markup (%)"
            error={form.formState.errors.percent?.message}
            hint="e.g. 15 bills events at provider cost + 15%."
          >
            {(id) => (
              <Input
                id={id}
                inputMode="decimal"
                placeholder="15"
                {...form.register("percent")}
              />
            )}
          </FormField>
          <FormField
            label={`Fixed uplift per event (${currency.toUpperCase()})`}
            error={form.formState.errors.fixed?.message}
            hint="A flat amount added to every event on top of the percentage. Use 0 for none."
          >
            {(id) => (
              <Input
                id={id}
                inputMode="decimal"
                placeholder="0.00"
                {...form.register("fixed")}
              />
            )}
          </FormField>
          {update.isError && (
            <p className="text-xs text-destructive">{problemMessage(update.error)}</p>
          )}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={update.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={update.isPending}>
              {update.isPending ? "Working…" : "Save markup"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
