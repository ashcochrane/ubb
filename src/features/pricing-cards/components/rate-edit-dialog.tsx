import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FormField } from "@/components/shared/form-field";
import { useCreateRate, useUpdateRate } from "../api/queries";
import { rateSchema, type RateFormValues } from "../lib/schema";

export interface RateEditDialogRate {
  id: string;
  metricName: string;
  label: string;
  unit: string;
  unitQuantity: number;
  currency: string;
  pricingType: "per_unit" | "flat";
  costPerUnitMicros: number;
  providerCostPerUnitMicros: number | null;
}

export interface RateEditDialogProps {
  cardId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  rate?: RateEditDialogRate;
}

const DEFAULTS: RateFormValues = {
  metricName: "",
  label: "",
  unit: "",
  unitQuantity: 1_000_000,
  pricingType: "per_unit",
  costPerUnitMicros: 0,
  providerCostPerUnitMicros: null,
};

export function RateEditDialog({
  cardId,
  open,
  onOpenChange,
  rate,
}: RateEditDialogProps) {
  const create = useCreateRate(cardId);
  const update = useUpdateRate(cardId);

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<RateFormValues>({
    resolver: zodResolver(rateSchema),
    defaultValues: DEFAULTS,
  });

  // Reset depends on primitive values (not the rate object) to avoid the same
  // infinite-render-in-tests trap that bit the customer detail page.
  const rateId = rate?.id;
  useEffect(() => {
    if (rate) {
      reset({
        metricName: rate.metricName,
        label: rate.label,
        unit: rate.unit,
        unitQuantity: rate.unitQuantity,
        pricingType: rate.pricingType,
        costPerUnitMicros: rate.costPerUnitMicros,
        providerCostPerUnitMicros: rate.providerCostPerUnitMicros,
      });
    } else {
      reset(DEFAULTS);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rateId, open, reset]);

  async function onSubmit(values: RateFormValues) {
    const body = {
      metricName: values.metricName.trim(),
      label: values.label,
      unit: values.unit,
      unitQuantity: values.unitQuantity,
      currency: "USD",
      pricingType: values.pricingType,
      costPerUnitMicros: values.costPerUnitMicros,
      providerCostPerUnitMicros: values.providerCostPerUnitMicros,
    };
    if (rate) {
      await update.mutateAsync({ rateId: rate.id, body });
    } else {
      await create.mutateAsync(body);
    }
    onOpenChange(false);
  }

  const pending = create.isPending || update.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{rate ? "Edit rate" : "New rate"}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <FormField label="Metric name" error={errors.metricName?.message}>
            {(id) => <Input id={id} {...register("metricName")} />}
          </FormField>
          <FormField label="Label" error={errors.label?.message}>
            {(id) => <Input id={id} {...register("label")} />}
          </FormField>
          <FormField label="Unit" error={errors.unit?.message}>
            {(id) => <Input id={id} {...register("unit")} />}
          </FormField>
          <FormField label="Pricing type" error={errors.pricingType?.message}>
            {(id) => (
              <select
                id={id}
                className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
                {...register("pricingType")}
              >
                <option value="per_unit">Per unit</option>
                <option value="flat">Flat</option>
              </select>
            )}
          </FormField>
          <FormField
            label="Cost per unit (micros)"
            error={errors.costPerUnitMicros?.message}
          >
            {(id) => (
              <Input
                id={id}
                type="number"
                min={0}
                {...register("costPerUnitMicros", { valueAsNumber: true })}
              />
            )}
          </FormField>
          <FormField
            label="Unit quantity (how many units the cost applies to)"
            hint="Default is 1,000,000 (cost is per million units)."
            error={errors.unitQuantity?.message}
          >
            {(id) => (
              <Input
                id={id}
                type="number"
                min={1}
                {...register("unitQuantity", { valueAsNumber: true })}
              />
            )}
          </FormField>
          <FormField
            label="Provider cost (micros, optional)"
            error={errors.providerCostPerUnitMicros?.message}
          >
            {(id) => (
              <Input
                id={id}
                type="number"
                min={0}
                {...register("providerCostPerUnitMicros", {
                  setValueAs: (v) => {
                    if (v === "" || v == null) return null;
                    const n = Number(v);
                    return Number.isFinite(n) ? n : null;
                  },
                })}
              />
            )}
          </FormField>
          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => onOpenChange(false)}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={pending}>
              {pending ? "Saving…" : "Save"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
