import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FormField } from "@/components/shared/form-field";
import { Section } from "@/components/shared/data-states";
import { useConfigureAutoTopUp } from "../api/queries";
import { autoTopUpSchema, type AutoTopUpFormValues } from "../lib/schema";

/**
 * Configure automatic prepaid top-ups. The API exposes only a write (PUT), so
 * this form sets policy rather than reflecting current server state.
 */
export function AutoTopUpForm({ customerId }: { customerId: string }) {
  const configure = useConfigureAutoTopUp(customerId);
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<AutoTopUpFormValues>({
    resolver: zodResolver(autoTopUpSchema),
    defaultValues: { isEnabled: false, threshold: 5, topUpAmount: 25 },
  });

  async function onSubmit(values: AutoTopUpFormValues) {
    await configure.mutateAsync({
      is_enabled: values.isEnabled,
      trigger_threshold_micros: Math.round(values.threshold * 1_000_000),
      top_up_amount_micros: Math.round(values.topUpAmount * 1_000_000),
    });
  }

  return (
    <Section
      title="Auto top-up"
      description="Automatically add funds when the balance runs low."
    >
      <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" className="size-4 accent-foreground" {...register("isEnabled")} />
          Enable auto top-up
        </label>
        <div className="grid gap-4 sm:grid-cols-2">
          <FormField
            label="Trigger below (USD)"
            error={errors.threshold?.message}
            hint="Top up when the balance falls under this."
          >
            {(id) => (
              <Input id={id} type="number" min={0} step={0.01} {...register("threshold", { valueAsNumber: true })} />
            )}
          </FormField>
          <FormField label="Top up by (USD)" error={errors.topUpAmount?.message}>
            {(id) => (
              <Input id={id} type="number" min={1} step={0.01} {...register("topUpAmount", { valueAsNumber: true })} />
            )}
          </FormField>
        </div>
        <Button type="submit" disabled={configure.isPending}>
          {configure.isPending ? "Saving…" : "Save auto top-up"}
        </Button>
      </form>
    </Section>
  );
}
