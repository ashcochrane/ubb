import { useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useForm } from "react-hook-form";

import { problemMessage } from "@/api/problem";
import { FormField } from "@/components/shared/form-field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select";
import { rewardTypeLabel } from "@/lib/labels";
import { cn } from "@/lib/utils";

import {
  emptyProgramFormValues,
  isRewardType,
  programFormSchema,
  REWARD_TYPES,
  type ProgramFormValues,
} from "../lib/program-form";

const REWARD_TYPE_HINTS: Record<string, string> = {
  flat_fee: "A fixed amount earned once per referred customer.",
  revenue_share: "Referrers earn a share of what their referred customers spend.",
  profit_share: "Referrers earn a share of the margin on referred usage (spend minus your provider cost).",
};

interface ProgramFormProps {
  mode: "create" | "edit";
  currency: string;
  defaultValues?: ProgramFormValues;
  pending: boolean;
  /** Server-side failure — shown near the submit, inputs preserved. */
  error: unknown;
  onSubmit: (values: ProgramFormValues) => void;
  submitLabel: string;
}

export function ProgramForm({
  mode,
  currency,
  defaultValues,
  pending,
  error,
  onSubmit,
  submitLabel,
}: ProgramFormProps) {
  const defaults = defaultValues ?? emptyProgramFormValues();
  const form = useForm<ProgramFormValues>({
    resolver: zodResolver(programFormSchema),
    defaultValues: defaults,
  });
  const errors = form.formState.errors;
  const rewardType = form.watch("reward_type");
  const currencyCode = currency.toUpperCase();

  const hasAdvancedValues =
    defaults.reward_window_days !== "" ||
    defaults.max_reward !== "" ||
    defaults.estimated_cost_percentage !== "" ||
    defaults.max_referrals_per_day !== "" ||
    defaults.min_customer_age_hours !== "";
  const [showAdvanced, setShowAdvanced] = useState(mode === "edit" && hasAdvancedValues);

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4" noValidate>
      <FormField
        label="Reward type"
        error={errors.reward_type?.message}
        hint={REWARD_TYPE_HINTS[rewardType]}
      >
        {(id) => (
          <Select
            value={rewardType}
            onValueChange={(value) => {
              if (typeof value === "string" && isRewardType(value)) {
                form.setValue("reward_type", value, { shouldValidate: form.formState.isSubmitted });
              }
            }}
          >
            <SelectTrigger id={id} className="w-full">
              <span>{rewardTypeLabel(rewardType)}</span>
            </SelectTrigger>
            <SelectContent>
              {REWARD_TYPES.map((type) => (
                <SelectItem key={type} value={type}>
                  {rewardTypeLabel(type)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        )}
      </FormField>

      <div className="grid gap-4 sm:grid-cols-2">
        <FormField
          label={rewardType === "flat_fee" ? `Reward amount (${currencyCode})` : "Reward percentage"}
          error={errors.reward_amount?.message}
          hint={
            rewardType === "flat_fee"
              ? "Entered in currency units — e.g. 5 means five dollars per referral."
              : "Percent between 0 and 100."
          }
        >
          {(id) => (
            <Input
              id={id}
              type="number"
              step="any"
              min="0"
              inputMode="decimal"
              placeholder={rewardType === "flat_fee" ? "5.00" : "10"}
              {...form.register("reward_amount")}
            />
          )}
        </FormField>
        <FormField
          label="Attribution window (days)"
          error={errors.attribution_window_days?.message}
          hint="How long after signup a new customer can still be attributed to a referrer (1–365)."
        >
          {(id) => (
            <Input
              id={id}
              type="number"
              step="1"
              min="1"
              max="365"
              {...form.register("attribution_window_days")}
            />
          )}
        </FormField>
      </div>

      <button
        type="button"
        onClick={() => setShowAdvanced((value) => !value)}
        className="flex items-center gap-1 text-[13px] font-medium text-text-secondary hover:text-text-primary"
        aria-expanded={showAdvanced}
      >
        {showAdvanced ? (
          <ChevronDown className="h-3.5 w-3.5" strokeWidth={2} />
        ) : (
          <ChevronRight className="h-3.5 w-3.5" strokeWidth={2} />
        )}
        Advanced settings
      </button>

      <div className={cn("grid gap-4 sm:grid-cols-2", !showAdvanced && "hidden")}>
        <FormField
          label="Reward window (days)"
          error={errors.reward_window_days?.message}
          hint="How long rewards keep accruing after attribution. Leave empty for no end."
        >
          {(id) => (
            <Input id={id} type="number" step="1" min="1" placeholder="No end" {...form.register("reward_window_days")} />
          )}
        </FormField>
        <FormField
          label={`Lifetime cap per referral (${currencyCode})`}
          error={errors.max_reward?.message}
          hint="The most any single referral can ever earn. Leave empty for no cap."
        >
          {(id) => (
            <Input id={id} type="number" step="any" min="0" placeholder="No cap" {...form.register("max_reward")} />
          )}
        </FormField>
        <FormField
          label="Estimated cost (%)"
          error={errors.estimated_cost_percentage?.message}
          hint="Optional planning figure: what you expect the program to cost as a share of referred spend."
        >
          {(id) => (
            <Input id={id} type="number" step="any" min="0" max="100" {...form.register("estimated_cost_percentage")} />
          )}
        </FormField>
        <FormField
          label="Max referrals per day"
          error={errors.max_referrals_per_day?.message}
          hint="Fraud guard: attributions beyond this daily count are refused."
        >
          {(id) => (
            <Input id={id} type="number" step="1" min="1" placeholder="No limit" {...form.register("max_referrals_per_day")} />
          )}
        </FormField>
        <FormField
          label="Minimum customer age (hours)"
          error={errors.min_customer_age_hours?.message}
          hint="Fraud guard: a referred customer must have existed at least this long before attribution."
        >
          {(id) => (
            <Input id={id} type="number" step="1" min="0" placeholder="None" {...form.register("min_customer_age_hours")} />
          )}
        </FormField>
      </div>

      {error ? <p className="text-xs text-destructive">{problemMessage(error)}</p> : null}

      <div className="flex justify-end">
        <Button type="submit" disabled={pending}>
          {pending ? "Working…" : submitLabel}
        </Button>
      </div>
    </form>
  );
}
