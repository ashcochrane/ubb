import { zodResolver } from "@hookform/resolvers/zod";
import { Info } from "lucide-react";
import { useForm } from "react-hook-form";

import { problemMessage } from "@/api/problem";
import { FormField } from "@/components/shared/form-field";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { isPostpaid } from "@/hooks/use-tenant-config";
import { WALLET_POLICY_TITLE } from "@/lib/control-family";
import { toastSuccess } from "@/lib/mutations";

import { useUpdateTenantConfig } from "../api/queries";
import type { TenantConfig } from "../api/types";
import {
  buildSpendPatch,
  configToSpendValues,
  spendControlSchema,
  type SpendControlValues,
} from "../lib/settings";

/** What the workspace's floors are — console copy beside the family's word (#468; slice 6 §5). */
const WALLET_POLICY_DESCRIPTION =
  "The workspace's default floors — a start is judged on a customer's balance less what is reserved for work already started, against these unless the customer has floors of their own.";

/**
 * The two balance floors, under Wallet policy's words. Values are entered in
 * currency units and PATCHed as integer micros — only changed fields are
 * sent, and clearing a clearable field sends an explicit null (omitted
 * fields are preserved server-side).
 *
 * THE DEFAULT CEILING LEFT THIS FORM (#453, slice 6 §2, §18). A ceiling on a
 * unit of work is a kernel setting, not a billing knob (#141 §7): the
 * workspace's two default ceilings — for work started with no declared kind,
 * one per altitude — are shown and edited on the Tasks page, beside the
 * declared kinds of work they stand in for. What stays here is what the wallet
 * governs.
 */
export function SpendLimitsForm({
  config,
  isAdmin,
}: {
  config: TenantConfig;
  isAdmin: boolean;
}) {
  const currency = config.default_currency.toUpperCase();
  const postpaid = isPostpaid(config);
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

  const heading = (
    <div>
      <p className="text-sm font-medium">{WALLET_POLICY_TITLE}</p>
      <p className="max-w-sm text-[13px] text-muted-foreground">{WALLET_POLICY_DESCRIPTION}</p>
    </div>
  );

  if (postpaid) {
    // Both floors are wallet floors, and postpaid usage never touches the
    // wallet — so there is nothing here to edit, and a form with no fields
    // would be a Save button for nothing.
    return (
      <div className="space-y-3">
        {heading}
        <Alert>
          <Info />
          <AlertDescription>
            The allowed-overdraft and wind-down floors aren't used under
            postpaid billing — usage drawdown skips the wallet entirely, so the
            spend gate never checks a balance floor. Each customer's spend pool
            is the control that applies instead.
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  return (
    <form
      onSubmit={(event) => void form.handleSubmit(onSubmit)(event)}
      className="space-y-4"
      noValidate
    >
      {heading}
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
          hint="How far into the allowed overdraft a balance may go before NEW top-level work is refused (running work may finish). 0 starts the wind-down as soon as a balance goes negative; a negative value starts it early, while the balance is still positive (−10 refuses new work once the balance drops below 10). Can't be more than the allowed overdraft — that's the hard stop point, where the stop signals fire. Leave empty for no wind-down floor — clearing removes it."
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
