import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FormField } from "@/components/shared/form-field";
import { useUpdatePlan } from "../api/queries";
import { updatePlanSchema, type UpdatePlanFormValues } from "../lib/schema";
import type { PlanUpdateIn } from "../api/types";

const toMicros = (dollars: number) => Math.round(dollars * 1_000_000);

/** Empty input → undefined ("leave unchanged"); otherwise a number for zod to validate. */
const toOptionalNumber = (v: unknown): number | undefined =>
  v === "" || v == null ? undefined : Number(v);

/** Re-price an existing plan by key. Leave a field blank to keep it unchanged. */
export function UpdatePlanForm() {
  const updatePlan = useUpdatePlan();
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<UpdatePlanFormValues>({
    resolver: zodResolver(updatePlanSchema),
    defaultValues: {
      key: "",
      accessFee: undefined,
      perSeat: undefined,
      migrateExisting: false,
    },
  });

  async function onSubmit(values: UpdatePlanFormValues) {
    const body: PlanUpdateIn = { migrate_existing: values.migrateExisting };
    if (values.accessFee !== undefined) body.access_fee_micros = toMicros(values.accessFee);
    if (values.perSeat !== undefined) body.per_seat_micros = toMicros(values.perSeat);
    await updatePlan.mutateAsync({ key: values.key, body });
    reset();
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField
          label="Plan key"
          error={errors.key?.message}
          hint="The key of the plan to re-price."
        >
          {(id) => <Input id={id} {...register("key")} placeholder="pro_monthly" />}
        </FormField>
        <div className="hidden sm:block" />
        <FormField
          label="New access fee (USD)"
          error={errors.accessFee?.message}
          hint="Blank leaves the current access fee unchanged."
        >
          {(id) => (
            <Input
              id={id}
              type="number"
              min={0}
              step="0.01"
              {...register("accessFee", { setValueAs: toOptionalNumber })}
            />
          )}
        </FormField>
        <FormField
          label="New per-seat price (USD)"
          error={errors.perSeat?.message}
          hint="Blank leaves the current per-seat price unchanged."
        >
          {(id) => (
            <Input
              id={id}
              type="number"
              min={0}
              step="0.01"
              {...register("perSeat", { setValueAs: toOptionalNumber })}
            />
          )}
        </FormField>
      </div>

      <label className="flex items-start gap-2.5 text-sm">
        <input
          type="checkbox"
          className="mt-0.5 size-4 accent-foreground"
          {...register("migrateExisting")}
        />
        <span>
          <span className="font-medium">Migrate existing subscribers</span>
          <span className="mt-0.5 block text-xs text-muted-foreground">
            Re-price current subscriptions onto the new price immediately (no proration). Leave
            off to grandfather existing subscribers on their old price — only new subscriptions
            get the new price.
          </span>
        </span>
      </label>

      <Button type="submit" size="sm" disabled={updatePlan.isPending}>
        {updatePlan.isPending ? "Updating…" : "Update plan"}
      </Button>
    </form>
  );
}
