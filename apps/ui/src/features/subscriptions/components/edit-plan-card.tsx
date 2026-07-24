// Edit plan by key: PATCH /platform/plans/{key}. The 200 response is untyped
// (a bare acknowledgement, unlike create's PlanOut), so on success the card
// echoes the values that were submitted rather than pretending to show the
// server's state.

import * as React from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { Controller, useForm } from "react-hook-form";

import { isNotFound, problemMessage } from "@/api/problem";
import { CopyButton } from "@/components/shared/copy-button";
import { DetailList } from "@/components/shared/detail-list";
import { FormField } from "@/components/shared/form-field";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useHasRole } from "@/hooks/use-current-role";
import { useTenantCurrency } from "@/hooks/use-tenant-config";
import { formatMicros } from "@/lib/format";
import { toastSuccess } from "@/lib/mutations";

import { useUpdatePlan } from "../api/queries";
import type { PlanUpdateIn } from "../api/types";
import { editPlanSchema, toPlanUpdateIn, type EditPlanFormValues } from "../lib/plan-form";

const DEFAULT_VALUES: EditPlanFormValues = {
  key: "",
  accessFee: "",
  perSeatFee: "",
  migrateExisting: false,
};

interface SubmittedUpdate {
  key: string;
  input: PlanUpdateIn;
}

export function EditPlanCard() {
  const currency = useTenantCurrency();
  const isAdmin = useHasRole("admin");
  const mutation = useUpdatePlan();
  const [applied, setApplied] = React.useState<SubmittedUpdate | null>(null);

  const form = useForm<EditPlanFormValues>({
    resolver: zodResolver(editPlanSchema),
    defaultValues: DEFAULT_VALUES,
  });
  const { errors } = form.formState;

  const onSubmit = form.handleSubmit((values) => {
    const input = toPlanUpdateIn(values);
    mutation.mutate(
      { key: values.key, input },
      {
        onSuccess: () => {
          setApplied({ key: values.key, input });
          toastSuccess("Plan updated", `New fees are live for "${values.key}".`);
        },
      },
    );
  });

  const unknownKey = isNotFound(mutation.error);
  const attemptedKey = mutation.variables?.key ?? "";

  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle>Edit a plan</CardTitle>
        <CardDescription>
          Change a plan's fees by key. Stripe Prices are immutable, so a fee edit mints a new
          versioned Price for each changed fee.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={(event) => void onSubmit(event)} className="flex flex-col gap-3" noValidate>
          <FormField
            label="Plan key"
            error={errors.key?.message}
            hint="The key you created the plan with. Plans can't be listed back from the API, so enter it from your own records."
          >
            {(id) => <Input id={id} className="font-mono" placeholder="team-monthly" {...form.register("key")} />}
          </FormField>
          <div className="grid gap-3 sm:grid-cols-2">
            <FormField
              label={`New access fee (${currency.toUpperCase()})`}
              error={errors.accessFee?.message}
              hint="Blank = leave unchanged."
            >
              {(id) => <Input id={id} inputMode="decimal" placeholder="129" {...form.register("accessFee")} />}
            </FormField>
            <FormField
              label={`New per-seat fee (${currency.toUpperCase()})`}
              error={errors.perSeatFee?.message}
              hint="Blank = leave unchanged."
            >
              {(id) => <Input id={id} inputMode="decimal" placeholder="18" {...form.register("perSeatFee")} />}
            </FormField>
          </div>

          <div className="flex items-start gap-3 rounded-lg border border-border p-3">
            <Controller
              control={form.control}
              name="migrateExisting"
              render={({ field }) => (
                <Switch
                  id="migrate-existing"
                  checked={field.value}
                  onCheckedChange={(checked) => field.onChange(checked)}
                  className="mt-0.5"
                />
              )}
            />
            <div className="flex flex-col gap-1">
              <Label htmlFor="migrate-existing">Migrate existing subscriptions</Label>
              <p className="text-xs text-muted-foreground">
                Changed fees get a new versioned Stripe Price either way. Left off, existing
                subscriptions are grandfathered on their old price and only new subscribers pay the
                new fees. Turned on, existing subscriptions are repointed to the new price with no
                proration.
              </p>
            </div>
          </div>

          {mutation.isError && (
            <p className="text-xs text-destructive">
              {unknownKey
                ? `No plan found with key "${attemptedKey}" — check the key and try again.`
                : problemMessage(mutation.error)}
            </p>
          )}
          <div className="flex items-center gap-3">
            <Button type="submit" disabled={mutation.isPending || !isAdmin}>
              {mutation.isPending ? "Working…" : "Update plan"}
            </Button>
            {!isAdmin && (
              <p className="text-xs text-muted-foreground">Editing plans requires the Admin role.</p>
            )}
          </div>
        </form>

        {applied && (
          <div className="mt-4 rounded-lg border border-border bg-muted/40 p-3">
            <p className="text-[13px] font-medium text-foreground">Update applied</p>
            <DetailList
              className="mt-1"
              items={[
                {
                  label: "Key",
                  value: (
                    <span className="inline-flex items-center gap-1.5">
                      <span className="font-mono text-[12px]">{applied.key}</span>
                      <CopyButton value={applied.key} label="Copy plan key" />
                    </span>
                  ),
                },
                {
                  label: "Access fee",
                  value:
                    applied.input.access_fee_micros == null
                      ? "Unchanged"
                      : formatMicros(applied.input.access_fee_micros, currency),
                },
                {
                  label: "Per-seat fee",
                  value:
                    applied.input.per_seat_micros == null
                      ? "Unchanged"
                      : formatMicros(applied.input.per_seat_micros, currency),
                },
                {
                  label: "Existing subscriptions",
                  value: applied.input.migrate_existing
                    ? "Migrated to the new price (no proration)"
                    : "Grandfathered on their old price",
                },
              ]}
            />
            <p className="mt-2 text-xs text-muted-foreground">
              The API acknowledges the update without returning the plan — these are the values you
              submitted.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
