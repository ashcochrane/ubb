import * as React from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";

import { ApiProblem, problemMessage } from "@/api/problem";
import { FormField } from "@/components/shared/form-field";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select";
import { useTenantCurrency } from "@/hooks/use-tenant-config";
import { pricingModelLabel } from "@/lib/labels";
import { cn } from "@/lib/utils";
import { toastSuccess } from "@/lib/mutations";
import { useAddRate } from "../api/queries";
import type { Book } from "../api/types";
import { UNIT_QUANTITY_CHOICES, toMicros } from "../lib/pricing-math";
import { buildRatePreview } from "../lib/rate-preview";
import {
  rateFormSchema,
  resolveUnitQuantity,
  type RateFormValues,
} from "../lib/schemas";

/** Add a live rate to a book. card_type and currency come from the book. */
export function AddRateDialog({
  book,
  open,
  onOpenChange,
}: {
  book: Book;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const currency = useTenantCurrency();
  const addRate = useAddRate(book.id);
  const defaults: RateFormValues = {
    measurement_key: "",
    provider: book.provider_key,
    event_type: "",
    task_type: "",
    rate_structure: "per_unit",
    rate: "",
    unit_choice: "1000000",
    custom_unit: "",
    fixed: "0",
  };
  const form = useForm<RateFormValues>({
    resolver: zodResolver(rateFormSchema),
    defaultValues: defaults,
  });

  React.useEffect(() => {
    if (open) {
      form.reset(defaults);
      addRate.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const values = form.watch();
  const preview = buildRatePreview(values, currency);

  const onSubmit = (formValues: RateFormValues) => {
    // The backend 422s this too — catch it before the round-trip.
    if (book.is_default && formValues.provider !== book.provider_key) {
      form.setError("provider", {
        message: `This book is the default for "${book.provider_key}" — rates must use that provider.`,
      });
      return;
    }
    addRate.mutate(
      {
        measurement_key: formValues.measurement_key,
        provider: formValues.provider,
        event_type: formValues.event_type,
        task_type: formValues.task_type,
        subtask_type: "",
        grouping_field_1: "",
        grouping_field_2: "",
        grouping_field_3: "",
        grouping_field_4: "",
        grouping_field_5: "",
        grouping_field_6: "",
        grouping_field_7: "",
        grouping_field_8: "",
        grouping_field_9: "",
        grouping_field_10: "",
        rate_structure: formValues.rate_structure,
        rate_per_unit_micros:
          formValues.rate_structure === "fixed_component"
            ? 0
            : toMicros(formValues.rate),
        unit_quantity:
          formValues.rate_structure === "fixed_component"
            ? 1
            : resolveUnitQuantity(formValues),
        fixed_micros: toMicros(formValues.fixed),
      },
      {
        onSuccess: (rate) => {
          toastSuccess("Rate added", `${rate.measurement_key} is pricing events now.`);
          onOpenChange(false);
        },
      },
    );
  };

  const errorMessage = addRate.isError
    ? addRate.error instanceof ApiProblem && addRate.error.code === "conflict"
      ? "An active rate with this exact identity (measurement key, provider, event type, dimensions) already exists in this book. Retire it first or change the matchers."
      : problemMessage(addRate.error)
    : null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add rate</DialogTitle>
          <DialogDescription>
            Rates go live immediately — new events matching this measurement key are
            priced with it. Currency and card type come from the book.
          </DialogDescription>
        </DialogHeader>
        <form
          onSubmit={(event) => void form.handleSubmit(onSubmit)(event)}
          className="space-y-4"
        >
          <FormField
            label="Measurement key"
            error={form.formState.errors.measurement_key?.message}
            hint="The measurement key this rate prices, e.g. gpt4o_input_tokens."
          >
            {(id) => (
              <Input
                id={id}
                className="font-mono"
                placeholder="gpt4o_input_tokens"
                {...form.register("measurement_key")}
              />
            )}
          </FormField>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <FormField
              label="Provider (optional)"
              error={form.formState.errors.provider?.message}
              hint={
                book.is_default
                  ? `Must be "${book.provider_key}" — this is the provider's default book.`
                  : undefined
              }
            >
              {(id) => (
                <Input id={id} className="font-mono" {...form.register("provider")} />
              )}
            </FormField>
            <FormField
              label="Event type (optional)"
              error={form.formState.errors.event_type?.message}
            >
              {(id) => (
                <Input
                  id={id}
                  className="font-mono"
                  placeholder="chat.completion"
                  {...form.register("event_type")}
                />
              )}
            </FormField>
          </div>
          <FormField
            label="Task type (optional)"
            error={form.formState.errors.task_type?.message}
            hint="Narrow the match to one task type."
          >
            {(id) => (
              <Input id={id} className="font-mono" {...form.register("task_type")} />
            )}
          </FormField>

          <div className="space-y-1.5">
            <Label>Rate structure</Label>
            <div className="flex gap-2">
              {(["per_unit", "fixed_component"] as const).map((model) => (
                <button
                  key={model}
                  type="button"
                  aria-pressed={values.rate_structure === model}
                  onClick={() => form.setValue("rate_structure", model)}
                  className={cn(
                    "rounded-lg border px-3 py-1.5 text-[13px] transition-colors",
                    values.rate_structure === model
                      ? "border-border-strong bg-bg-subtle font-medium"
                      : "border-border hover:bg-bg-subtle/50",
                  )}
                >
                  {pricingModelLabel(model)}
                </button>
              ))}
            </div>
            <p className="text-xs text-muted-foreground">
              {values.rate_structure === "fixed_component"
                ? "Fixed component: every matching event charges the fixed amount, regardless of units."
                : "Per unit: the amount below is charged per chosen quantity of units."}
            </p>
          </div>

          {values.rate_structure === "per_unit" && (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <FormField
                label={`Rate (${currency.toUpperCase()})`}
                error={form.formState.errors.rate?.message}
              >
                {(id) => (
                  <Input
                    id={id}
                    inputMode="decimal"
                    placeholder="2.50"
                    {...form.register("rate")}
                  />
                )}
              </FormField>
              <div className="flex flex-col gap-1.5">
                <Label>Per</Label>
                <Select
                  value={values.unit_choice}
                  onValueChange={(choice) =>
                    form.setValue("unit_choice", choice as RateFormValues["unit_choice"])
                  }
                >
                  <SelectTrigger className="w-full" aria-label="Unit quantity">
                    {UNIT_QUANTITY_CHOICES.find((c) => c.value === values.unit_choice)
                      ?.label ?? "per unit"}
                  </SelectTrigger>
                  <SelectContent>
                    {UNIT_QUANTITY_CHOICES.map((choice) => (
                      <SelectItem key={choice.value} value={choice.value}>
                        {choice.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {values.unit_choice === "custom" && (
                  <>
                    <Input
                      inputMode="numeric"
                      placeholder="Units, e.g. 500"
                      aria-label="Custom unit quantity"
                      {...form.register("custom_unit")}
                    />
                    {form.formState.errors.custom_unit && (
                      <p className="text-xs text-destructive">
                        {form.formState.errors.custom_unit.message}
                      </p>
                    )}
                  </>
                )}
              </div>
            </div>
          )}

          <FormField
            label={`Fixed amount per event (${currency.toUpperCase()})`}
            error={form.formState.errors.fixed?.message}
            hint={
              values.rate_structure === "fixed_component"
                ? "The fixed charge for every matching event."
                : "Optional fixed add-on charged in addition to the per-unit amount. Use 0 for none."
            }
          >
            {(id) => (
              <Input id={id} inputMode="decimal" {...form.register("fixed")} />
            )}
          </FormField>

          {preview && (
            <p className="rounded-lg bg-bg-subtle px-3 py-2 text-[12px] text-text-secondary">
              {preview}
            </p>
          )}
          {errorMessage && <p className="text-xs text-destructive">{errorMessage}</p>}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={addRate.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={addRate.isPending}>
              {addRate.isPending ? "Working…" : "Add rate"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
