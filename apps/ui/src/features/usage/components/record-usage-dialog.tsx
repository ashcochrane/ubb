import { useState, type ReactElement } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FormField } from "@/components/shared/form-field";
import { useRecordUsage } from "../api/queries";
import type { RecordUsageRequest } from "../api/types";
import {
  recordUsageSchema,
  recordUsageDefaults,
  dollarsToMicros,
  textToInt,
  orUndefined,
  type RecordUsageFormValues,
} from "../lib/schema";

/**
 * Advanced dialog for recording a single usage event. `request_id` and
 * `idempotency_key` are generated per submit; dollar costs are converted to
 * integer micros. Optional fields are omitted when blank.
 */
export function RecordUsageDialog({ trigger }: { trigger: ReactElement }) {
  const [open, setOpen] = useState(false);
  const record = useRecordUsage();
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<RecordUsageFormValues>({
    resolver: zodResolver(recordUsageSchema),
    defaultValues: recordUsageDefaults,
  });

  async function onSubmit(values: RecordUsageFormValues) {
    const body: RecordUsageRequest = {
      customer_id: values.customer_id.trim(),
      request_id: crypto.randomUUID(),
      idempotency_key: crypto.randomUUID(),
      event_type: orUndefined(values.event_type),
      provider: orUndefined(values.provider),
      product_id: orUndefined(values.product_id),
      task_id: orUndefined(values.task_id),
      currency: orUndefined(values.currency),
      units: textToInt(values.units),
      provider_cost_micros: dollarsToMicros(values.provider_cost),
      billed_cost_micros: dollarsToMicros(values.billed_cost),
    };
    await record.mutateAsync(body);
    setOpen(false);
    reset();
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={trigger} />
      <DialogContent className="max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Record usage</DialogTitle>
          <DialogDescription>
            Manually record a single usage event. An idempotency key and request
            ID are generated automatically.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <FormField label="Customer ID" error={errors.customer_id?.message}>
            {(id) => <Input id={id} {...register("customer_id")} />}
          </FormField>
          <div className="grid grid-cols-2 gap-3">
            <FormField label="Event type" error={errors.event_type?.message}>
              {(id) => (
                <Input id={id} placeholder="e.g. chat.completion" {...register("event_type")} />
              )}
            </FormField>
            <FormField label="Provider" error={errors.provider?.message}>
              {(id) => <Input id={id} placeholder="e.g. openai" {...register("provider")} />}
            </FormField>
            <FormField label="Product ID" error={errors.product_id?.message}>
              {(id) => <Input id={id} {...register("product_id")} />}
            </FormField>
            <FormField label="Task ID" error={errors.task_id?.message}>
              {(id) => <Input id={id} {...register("task_id")} />}
            </FormField>
            <FormField label="Units" error={errors.units?.message}>
              {(id) => <Input id={id} inputMode="numeric" {...register("units")} />}
            </FormField>
            <FormField label="Currency" error={errors.currency?.message}>
              {(id) => <Input id={id} placeholder="usd" {...register("currency")} />}
            </FormField>
            <FormField
              label="Provider cost (USD)"
              hint="What the upstream provider charged you"
              error={errors.provider_cost?.message}
            >
              {(id) => (
                <Input id={id} inputMode="decimal" placeholder="0.00" {...register("provider_cost")} />
              )}
            </FormField>
            <FormField
              label="Billed cost (USD)"
              hint="What you charge the customer"
              error={errors.billed_cost?.message}
            >
              {(id) => (
                <Input id={id} inputMode="decimal" placeholder="0.00" {...register("billed_cost")} />
              )}
            </FormField>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={record.isPending}>
              {record.isPending ? "Recording…" : "Record usage"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
