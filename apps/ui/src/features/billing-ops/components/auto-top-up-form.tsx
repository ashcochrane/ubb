import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FormField } from "@/components/shared/form-field";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useConfigureAutoTopUp } from "../api/queries";
import { autoTopUpSchema, type AutoTopUpFormValues } from "../lib/schema";

export function AutoTopUpForm({ customerId }: { customerId: string }) {
  const configure = useConfigureAutoTopUp(customerId);
  const { register, handleSubmit, formState: { errors } } =
    useForm<AutoTopUpFormValues>({
      resolver: zodResolver(autoTopUpSchema),
      defaultValues: { isEnabled: false, threshold: 5, topUpAmount: 25 },
    });

  async function onSubmit(values: AutoTopUpFormValues) {
    await configure.mutateAsync({
      isEnabled: values.isEnabled,
      triggerThresholdMicros: Math.round(values.threshold * 1_000_000),
      topUpAmountMicros: Math.round(values.topUpAmount * 1_000_000),
    });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Auto top-up</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" {...register("isEnabled")} />
            Enable auto top-up
          </label>
          <FormField
            label="Trigger when balance falls below (USD)"
            error={errors.threshold?.message}
          >
            {(id) => (
              <Input
                id={id}
                type="number"
                min={0}
                step={0.01}
                {...register("threshold", { valueAsNumber: true })}
              />
            )}
          </FormField>
          <FormField
            label="Top up by (USD)"
            error={errors.topUpAmount?.message}
          >
            {(id) => (
              <Input
                id={id}
                type="number"
                min={1}
                step={0.01}
                {...register("topUpAmount", { valueAsNumber: true })}
              />
            )}
          </FormField>
          <Button type="submit" disabled={configure.isPending}>
            {configure.isPending ? "Saving…" : "Save"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
