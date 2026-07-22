import { useState } from "react";
import { Controller, useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { FormField } from "@/components/shared/form-field";
import { CopyField, DetailGrid, DetailRow } from "@/components/shared/data-states";
import { formatMicros, humanizeLabel } from "@/lib/format";
import { useCreatePlan } from "../api/queries";
import { createPlanSchema, type CreatePlanFormValues } from "../lib/schema";
import type { PlanOut } from "../api/types";

const toMicros = (dollars: number) => Math.round(dollars * 1_000_000);

/** Blind create (there is no list endpoint) — surface the returned plan on success. */
export function CreatePlanForm() {
  const [created, setCreated] = useState<PlanOut | null>(null);
  const createPlan = useCreatePlan();
  const {
    register,
    control,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<CreatePlanFormValues>({
    resolver: zodResolver(createPlanSchema),
    defaultValues: {
      key: "",
      name: "",
      accessFee: 0,
      perSeat: 0,
      interval: "month",
    },
  });

  async function onSubmit(values: CreatePlanFormValues) {
    const plan = await createPlan.mutateAsync({
      key: values.key,
      name: values.name,
      access_fee_micros: toMicros(values.accessFee),
      per_seat_micros: toMicros(values.perSeat),
      interval: values.interval,
    });
    setCreated(plan);
  }

  if (created) {
    return (
      <div className="space-y-4">
        <DetailGrid>
          <DetailRow label="Name">{created.name}</DetailRow>
          <DetailRow label="Key">
            <CopyField value={created.key} />
          </DetailRow>
          <DetailRow label="Access fee">
            {formatMicros(created.access_fee_micros)} / {humanizeLabel(created.interval)}
          </DetailRow>
          <DetailRow label="Per seat">
            {formatMicros(created.per_seat_micros)} / {humanizeLabel(created.interval)}
          </DetailRow>
        </DetailGrid>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            setCreated(null);
            reset();
          }}
        >
          Create another
        </Button>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField
          label="Plan key"
          error={errors.key?.message}
          hint="Stable identifier used to reference this plan (e.g. pro_monthly)."
        >
          {(id) => <Input id={id} {...register("key")} placeholder="pro_monthly" />}
        </FormField>
        <FormField label="Display name" error={errors.name?.message}>
          {(id) => <Input id={id} {...register("name")} placeholder="Pro" />}
        </FormField>
        <FormField
          label="Access fee (USD)"
          error={errors.accessFee?.message}
          hint="Flat recurring fee per interval."
        >
          {(id) => (
            <Input
              id={id}
              type="number"
              min={0}
              step="0.01"
              {...register("accessFee", { valueAsNumber: true })}
            />
          )}
        </FormField>
        <FormField
          label="Per-seat price (USD)"
          error={errors.perSeat?.message}
          hint="Charged per seat, per interval."
        >
          {(id) => (
            <Input
              id={id}
              type="number"
              min={0}
              step="0.01"
              {...register("perSeat", { valueAsNumber: true })}
            />
          )}
        </FormField>
        <FormField label="Billing interval" error={errors.interval?.message}>
          {(id) => (
            <Controller
              control={control}
              name="interval"
              render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger id={id} className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="month">Monthly</SelectItem>
                    <SelectItem value="year">Yearly</SelectItem>
                  </SelectContent>
                </Select>
              )}
            />
          )}
        </FormField>
      </div>
      <Button type="submit" size="sm" disabled={createPlan.isPending}>
        {createPlan.isPending ? "Creating…" : "Create plan"}
      </Button>
    </form>
  );
}
