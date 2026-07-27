import { useForm, useWatch, Controller } from "react-hook-form";
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
import { humanizeLabel } from "@/lib/format";
import {
  programSchema,
  programToForm,
  toProgramCreate,
  toProgramUpdate,
  type ProgramFormValues,
} from "../lib/schema";
import { rewardValueHint, rewardValueLabel } from "../lib/reward";
import { REWARD_TYPES, type Program, type RewardType } from "../api/types";
import { useCreateProgram, useUpdateProgram } from "../api/queries";

const EMPTY: ProgramFormValues = {
  reward_type: "flat_fee",
  reward_value: "",
  attribution_window_days: "30",
  reward_window_days: "",
  max_reward_dollars: "",
  estimated_cost_percentage: "",
  max_referrals_per_day: "",
  min_customer_age_hours: "",
};

/**
 * Create/edit form for the referral program. Used inline when no program
 * exists yet, and inside a dialog to edit an existing one.
 */
export function ProgramForm({
  existing,
  onDone,
}: {
  existing?: Program;
  onDone?: () => void;
}) {
  const isEdit = Boolean(existing);
  const create = useCreateProgram();
  const update = useUpdateProgram();

  const form = useForm<ProgramFormValues>({
    resolver: zodResolver(programSchema),
    defaultValues: existing ? programToForm(existing) : EMPTY,
  });
  const { errors } = form.formState;
  const rewardType = useWatch({ control: form.control, name: "reward_type" }) as RewardType;

  const onSubmit = form.handleSubmit(async (values) => {
    if (isEdit) {
      await update.mutateAsync(toProgramUpdate(values));
    } else {
      await create.mutateAsync(toProgramCreate(values));
    }
    onDone?.();
  });

  const pending = create.isPending || update.isPending;

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField label="Reward model" error={errors.reward_type?.message}>
          {(id) => (
            <Controller
              control={form.control}
              name="reward_type"
              render={({ field }) => (
                <Select
                  value={field.value}
                  onValueChange={(v) => field.onChange(v as RewardType)}
                >
                  <SelectTrigger id={id} className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {REWARD_TYPES.map((rt) => (
                      <SelectItem key={rt} value={rt}>
                        {humanizeLabel(rt)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            />
          )}
        </FormField>

        <FormField
          label={rewardValueLabel(rewardType)}
          error={errors.reward_value?.message}
          hint={rewardValueHint(rewardType)}
        >
          {(id) => (
            <Input
              id={id}
              type="number"
              step="0.01"
              min={0}
              {...form.register("reward_value")}
            />
          )}
        </FormField>

        <FormField
          label="Attribution window (days)"
          error={errors.attribution_window_days?.message}
          hint="How long after signup a referral can be attributed."
        >
          {(id) => (
            <Input
              id={id}
              type="number"
              min={1}
              {...form.register("attribution_window_days")}
            />
          )}
        </FormField>

        <FormField
          label="Reward window (days)"
          error={errors.reward_window_days?.message}
          hint="Optional — how long rewards keep accruing."
        >
          {(id) => (
            <Input
              id={id}
              type="number"
              min={0}
              {...form.register("reward_window_days")}
            />
          )}
        </FormField>

        <FormField
          label="Max reward (USD)"
          error={errors.max_reward_dollars?.message}
          hint="Optional cap on total reward per referral."
        >
          {(id) => (
            <Input
              id={id}
              type="number"
              step="0.01"
              min={0}
              {...form.register("max_reward_dollars")}
            />
          )}
        </FormField>

        <FormField
          label="Estimated cost (%)"
          error={errors.estimated_cost_percentage?.message}
          hint="Optional — used for cost projections."
        >
          {(id) => (
            <Input
              id={id}
              type="number"
              step="0.01"
              min={0}
              {...form.register("estimated_cost_percentage")}
            />
          )}
        </FormField>

        <FormField
          label="Max referrals / day"
          error={errors.max_referrals_per_day?.message}
          hint="Optional fraud limit per referrer."
        >
          {(id) => (
            <Input
              id={id}
              type="number"
              min={0}
              {...form.register("max_referrals_per_day")}
            />
          )}
        </FormField>

        <FormField
          label="Min customer age (hours)"
          error={errors.min_customer_age_hours?.message}
          hint="Optional — minimum account age before a referral counts."
        >
          {(id) => (
            <Input
              id={id}
              type="number"
              min={0}
              {...form.register("min_customer_age_hours")}
            />
          )}
        </FormField>
      </div>

      <div className="flex justify-end gap-2">
        {onDone && (
          <Button
            type="button"
            variant="outline"
            disabled={pending}
            onClick={onDone}
          >
            Cancel
          </Button>
        )}
        <Button type="submit" disabled={pending}>
          {pending
            ? "Saving…"
            : isEdit
              ? "Save changes"
              : "Create program"}
        </Button>
      </div>
    </form>
  );
}
