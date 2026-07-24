import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";

import { problemMessage } from "@/api/problem";
import { FormField } from "@/components/shared/form-field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { toastSuccess } from "@/lib/mutations";

import { useUpdateTenantConfig } from "../api/queries";
import type { TenantConfig } from "../api/types";
import {
  buildSpendPatch,
  configToSpendValues,
  spendControlSchema,
  type SpendControlValues,
} from "../lib/settings";

/**
 * The four money defaults. Values are entered in currency units and PATCHed
 * as integer micros — only changed fields are sent, and clearing a clearable
 * field sends an explicit null (omitted fields are preserved server-side).
 */
export function SpendLimitsForm({
  config,
  isAdmin,
}: {
  config: TenantConfig;
  isAdmin: boolean;
}) {
  const currency = config.default_currency.toUpperCase();
  const mutation = useUpdateTenantConfig();
  const form = useForm<SpendControlValues>({
    resolver: zodResolver(spendControlSchema),
    defaultValues: configToSpendValues(config),
  });
  const errors = form.formState.errors;

  const onSubmit = (values: SpendControlValues) => {
    const patch = buildSpendPatch(config, values);
    if (Object.keys(patch).length === 0) return;
    mutation.mutate(patch, {
      onSuccess: (updated) => {
        form.reset(configToSpendValues(updated));
        toastSuccess("Spend control settings saved");
      },
    });
  };

  return (
    <form
      onSubmit={(event) => void form.handleSubmit(onSubmit)(event)}
      className="space-y-4"
      noValidate
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField
          label={`Allowed overdraft (${currency})`}
          error={errors.allowedOverdraft?.message}
          hint="How far below zero a customer's balance may go before the customer-wide stop signal fires. 0 means the stop fires as soon as a balance goes negative. This is an allowed overdraft, not a reserve to keep."
        >
          {(id) => (
            <Input
              id={id}
              type="number"
              step="any"
              min="0"
              disabled={!isAdmin}
              {...form.register("allowedOverdraft")}
            />
          )}
        </FormField>
        <FormField
          label={`Wind-down floor (${currency})`}
          error={errors.softFloor?.message}
          hint="Balance at which NEW jobs are refused while running work is allowed to finish. May be negative, but never below the hard stop point. Leave empty for no wind-down floor — clearing removes it."
        >
          {(id) => (
            <Input
              id={id}
              type="number"
              step="any"
              disabled={!isAdmin}
              placeholder="None"
              {...form.register("softFloor")}
            />
          )}
        </FormField>
        <FormField
          label={`Default task spend limit (${currency})`}
          error={errors.taskLimit?.message}
          hint="Provider-cost budget applied to each new task unless the start call sets its own. A task that crosses it is stopped. Leave empty for no default limit."
        >
          {(id) => (
            <Input
              id={id}
              type="number"
              step="any"
              disabled={!isAdmin}
              placeholder="None"
              {...form.register("taskLimit")}
            />
          )}
        </FormField>
        <FormField
          label={`Default task floor snapshot (${currency})`}
          error={errors.taskFloorSnapshot?.message}
          hint="Advanced: balance floor recorded on each task at start when the start call doesn't provide one. Leave empty for none."
        >
          {(id) => (
            <Input
              id={id}
              type="number"
              step="any"
              disabled={!isAdmin}
              placeholder="None"
              {...form.register("taskFloorSnapshot")}
            />
          )}
        </FormField>
      </div>

      {mutation.isError && (
        <p className="text-xs text-destructive">
          {problemMessage(mutation.error)}
        </p>
      )}

      <div className="flex justify-end">
        <Button
          type="submit"
          size="sm"
          disabled={!isAdmin || mutation.isPending || !form.formState.isDirty}
        >
          {mutation.isPending ? "Working…" : "Save spend settings"}
        </Button>
      </div>
    </form>
  );
}
