import { useState, type ReactNode } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogClose,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FormField } from "@/components/shared/form-field";
import { useAddRate } from "../api/queries";
import {
  rateCreateSchema,
  PRICING_MODELS,
  type RateCreateValues,
} from "../lib/schema";

const SELECT_CLASS =
  "h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50";

/** Add a single provider rate to a rate card. Money is entered in dollars. */
export function AddRateDialog({
  bookId,
  trigger,
}: {
  bookId: string;
  trigger: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const add = useAddRate(bookId);

  const form = useForm<RateCreateValues>({
    resolver: zodResolver(rateCreateSchema),
    defaultValues: {
      metric_name: "",
      provider: "",
      event_type: "",
      pricing_model: "per_unit",
      rate_per_unit: 0,
      unit_quantity: 1_000_000,
      fixed: 0,
      product_id: "",
    },
  });
  const { errors } = form.formState;

  const onSubmit = form.handleSubmit(async (values) => {
    await add.mutateAsync({
      metric_name: values.metric_name,
      provider: values.provider,
      event_type: values.event_type,
      pricing_model: values.pricing_model,
      rate_per_unit_micros: Math.round(values.rate_per_unit * 1_000_000),
      unit_quantity: values.unit_quantity,
      fixed_micros: Math.round(values.fixed * 1_000_000),
      product_id: values.product_id,
    });
    setOpen(false);
    form.reset();
  });

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        setOpen(v);
        if (!v) form.reset();
      }}
    >
      <DialogTrigger render={trigger as React.ReactElement} />
      <DialogContent className="sm:max-w-md">
        <form onSubmit={onSubmit}>
          <DialogHeader>
            <DialogTitle>Add rate</DialogTitle>
            <DialogDescription>
              Add a provider rate to this card. Prices are entered in dollars.
            </DialogDescription>
          </DialogHeader>

          <div className="mt-4 flex flex-col gap-4">
            <FormField label="Metric name" error={errors.metric_name?.message}>
              {(id) => (
                <Input id={id} placeholder="input_tokens" {...form.register("metric_name")} />
              )}
            </FormField>

            <div className="grid grid-cols-2 gap-4">
              <FormField label="Provider" error={errors.provider?.message}>
                {(id) => (
                  <Input id={id} placeholder="openai" {...form.register("provider")} />
                )}
              </FormField>
              <FormField label="Event type" error={errors.event_type?.message}>
                {(id) => (
                  <Input id={id} placeholder="completion" {...form.register("event_type")} />
                )}
              </FormField>
            </div>

            <FormField label="Pricing model" error={errors.pricing_model?.message}>
              {(id) => (
                <select id={id} className={SELECT_CLASS} {...form.register("pricing_model")}>
                  {PRICING_MODELS.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              )}
            </FormField>

            <div className="grid grid-cols-2 gap-4">
              <FormField
                label="Rate per unit (USD)"
                error={errors.rate_per_unit?.message}
              >
                {(id) => (
                  <Input
                    id={id}
                    type="number"
                    min={0}
                    step="any"
                    {...form.register("rate_per_unit", { valueAsNumber: true })}
                  />
                )}
              </FormField>
              <FormField
                label="Unit quantity"
                error={errors.unit_quantity?.message}
                hint="Units the rate applies per (e.g. 1,000,000)."
              >
                {(id) => (
                  <Input
                    id={id}
                    type="number"
                    min={1}
                    step={1}
                    {...form.register("unit_quantity", { valueAsNumber: true })}
                  />
                )}
              </FormField>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <FormField label="Fixed fee (USD)" error={errors.fixed?.message}>
                {(id) => (
                  <Input
                    id={id}
                    type="number"
                    min={0}
                    step="any"
                    {...form.register("fixed", { valueAsNumber: true })}
                  />
                )}
              </FormField>
              <FormField label="Product ID" error={errors.product_id?.message}>
                {(id) => <Input id={id} {...form.register("product_id")} />}
              </FormField>
            </div>
          </div>

          <DialogFooter className="mt-2">
            <DialogClose render={<Button variant="outline" type="button" disabled={add.isPending} />}>
              Cancel
            </DialogClose>
            <Button type="submit" disabled={add.isPending}>
              {add.isPending ? "Adding…" : "Add rate"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
