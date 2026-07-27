import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";

import { problemMessage } from "@/api/problem";
import { DisabledHint } from "@/components/shared/disabled-hint";
import { ErrorCard } from "@/components/shared/error-card";
import { FormField } from "@/components/shared/form-field";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { toastSuccess } from "@/lib/mutations";

import { useMarginThreshold, useUpdateMarginThreshold } from "../api/queries";
import type { MarginThreshold } from "../api/types";
import {
  marginAlertSchema,
  thresholdToValues,
  valuesToThreshold,
  type MarginAlertValues,
} from "../lib/settings";

/**
 * Tenant-level margin-alert configuration (GET/PUT /margin/threshold): the
 * rules that decide when a customer shows up in the Overview's
 * unprofitable-customers alert and when a provider-cost spike raises an
 * event. Server defaults when never configured: 0% / 1 period / 25% spike.
 */
export function MarginAlertCard({ isAdmin }: { isAdmin: boolean }) {
  const threshold = useMarginThreshold();

  return (
    <Card>
      <CardHeader>
        <CardTitle>Margin alerts</CardTitle>
        <CardDescription>
          When a customer counts as unprofitable, and when a jump in provider
          cost raises an alert. These rules drive the unprofitable-customers
          alert on the Overview.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {threshold.isLoading ? (
          <div className="grid gap-4 sm:grid-cols-3">
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
            <Skeleton className="h-16 w-full" />
          </div>
        ) : threshold.isError || !threshold.data ? (
          <ErrorCard
            error={threshold.error}
            onRetry={() => void threshold.refetch()}
            title="Couldn't load the margin alert settings"
          />
        ) : (
          <MarginAlertForm threshold={threshold.data} isAdmin={isAdmin} />
        )}
      </CardContent>
    </Card>
  );
}

function MarginAlertForm({
  threshold,
  isAdmin,
}: {
  threshold: MarginThreshold;
  isAdmin: boolean;
}) {
  const mutation = useUpdateMarginThreshold();
  const form = useForm<MarginAlertValues>({
    resolver: zodResolver(marginAlertSchema),
    defaultValues: thresholdToValues(threshold),
  });
  const errors = form.formState.errors;

  const onSubmit = (values: MarginAlertValues) => {
    mutation.mutate(valuesToThreshold(values), {
      onSuccess: (updated) => {
        form.reset(thresholdToValues(updated));
        toastSuccess("Margin alert settings saved");
      },
    });
  };

  return (
    <form
      onSubmit={(event) => void form.handleSubmit(onSubmit)(event)}
      className="space-y-4"
      noValidate
    >
      <div className="grid gap-4 sm:grid-cols-3">
        <FormField
          label="Minimum margin (%)"
          error={errors.minMarginPct?.message}
          hint="Customers whose margin stays below this percentage count as unprofitable. 0 flags only customers who cost more than they earn you."
        >
          {(id) => (
            <Input
              id={id}
              type="number"
              step="any"
              disabled={!isAdmin}
              {...form.register("minMarginPct")}
            />
          )}
        </FormField>
        <FormField
          label="Consecutive periods"
          error={errors.consecutivePeriods?.message}
          hint="How many periods in a row a customer must stay below the minimum before being flagged. 1 flags after a single period."
        >
          {(id) => (
            <Input
              id={id}
              type="number"
              step="1"
              min="1"
              disabled={!isAdmin}
              {...form.register("consecutivePeriods")}
            />
          )}
        </FormField>
        <FormField
          label="Provider-cost spike (%)"
          error={errors.providerCostSpikePct?.message}
          hint="A jump in a customer's provider cost of more than this percentage from one period to the next raises a cost-spike event."
        >
          {(id) => (
            <Input
              id={id}
              type="number"
              step="any"
              disabled={!isAdmin}
              {...form.register("providerCostSpikePct")}
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
        <DisabledHint disabled={!isAdmin} hint="Requires the Admin role.">
          <Button
            type="submit"
            size="sm"
            disabled={!isAdmin || mutation.isPending || !form.formState.isDirty}
          >
            {mutation.isPending ? "Working…" : "Save margin alerts"}
          </Button>
        </DisabledHint>
      </div>
    </form>
  );
}
