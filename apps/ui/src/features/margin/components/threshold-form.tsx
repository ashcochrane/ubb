import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { FormField } from "@/components/shared/form-field";
import { Section, LoadingRows, ErrorInline } from "@/components/shared/data-states";
import { useMarginThreshold, useSaveThreshold } from "../api/queries";
import { thresholdSchema, type ThresholdValues } from "../lib/schema";

export function ThresholdForm() {
  const query = useMarginThreshold();
  const save = useSaveThreshold();

  const form = useForm<ThresholdValues>({
    resolver: zodResolver(thresholdSchema),
    defaultValues: {
      min_margin_pct: 0,
      consecutive_periods: 1,
      provider_cost_spike_pct: 25,
    },
  });
  const { reset, register, handleSubmit, formState } = form;

  // Prefill once the current threshold loads.
  useEffect(() => {
    if (query.data) {
      reset({
        min_margin_pct: query.data.min_margin_pct,
        consecutive_periods: query.data.consecutive_periods,
        provider_cost_spike_pct: query.data.provider_cost_spike_pct,
      });
    }
  }, [query.data, reset]);

  const onSubmit = handleSubmit((values) => save.mutate(values));
  const { errors } = formState;

  return (
    <Section
      title="Unprofitability alerts"
      description="These thresholds drive which customers are flagged as unprofitable and when provider-cost spikes raise an alert."
    >
      {query.isLoading ? (
        <LoadingRows rows={3} />
      ) : query.isError ? (
        <ErrorInline error={query.error} onRetry={query.refetch} />
      ) : (
        <form onSubmit={onSubmit} className="flex max-w-md flex-col gap-4">
          <FormField
            label="Minimum margin %"
            error={errors.min_margin_pct?.message}
            hint="A customer below this gross margin percentage is flagged."
          >
            {(id) => (
              <Input
                id={id}
                type="number"
                step="0.1"
                {...register("min_margin_pct", { valueAsNumber: true })}
              />
            )}
          </FormField>

          <FormField
            label="Consecutive periods"
            error={errors.consecutive_periods?.message}
            hint="How many periods in a row a customer must stay below the threshold before alerting."
          >
            {(id) => (
              <Input
                id={id}
                type="number"
                step="1"
                {...register("consecutive_periods", { valueAsNumber: true })}
              />
            )}
          </FormField>

          <FormField
            label="Provider cost spike %"
            error={errors.provider_cost_spike_pct?.message}
            hint="A period-over-period jump in provider cost above this percentage raises a spike alert."
          >
            {(id) => (
              <Input
                id={id}
                type="number"
                step="1"
                {...register("provider_cost_spike_pct", { valueAsNumber: true })}
              />
            )}
          </FormField>

          <div>
            <Button type="submit" disabled={save.isPending}>
              {save.isPending ? "Saving…" : "Save thresholds"}
            </Button>
          </div>
        </form>
      )}
    </Section>
  );
}
