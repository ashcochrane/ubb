// Create plan: POST /platform/plans. The 201 response (PlanOut) is shown in a
// result card — the only place the created plan is ever visible, since the
// API has no plans-list endpoint.

import * as React from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { Controller, useForm } from "react-hook-form";

import { ApiProblem, problemMessage } from "@/api/problem";
import { CopyButton } from "@/components/shared/copy-button";
import { DetailList } from "@/components/shared/detail-list";
import { FormField } from "@/components/shared/form-field";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useHasRole } from "@/hooks/use-current-role";
import { useTenantCurrency } from "@/hooks/use-tenant-config";
import { formatMicros } from "@/lib/format";
import { planIntervalLabel } from "@/lib/labels";
import { toastSuccess } from "@/lib/mutations";

import { useCreatePlan } from "../api/queries";
import type { PlanOut } from "../api/types";
import {
  createPlanSchema,
  toPlanIn,
  type CreatePlanFormValues,
  type IntervalChoice,
} from "../lib/plan-form";

const DEFAULT_VALUES: CreatePlanFormValues = {
  key: "",
  name: "",
  accessFee: "",
  perSeatFee: "",
  intervalChoice: "month",
  customInterval: "",
};

function intervalChoiceText(choice: IntervalChoice): string {
  return choice === "custom" ? "Custom…" : planIntervalLabel(choice);
}

export function CreatePlanCard() {
  const currency = useTenantCurrency();
  const isAdmin = useHasRole("admin");
  const mutation = useCreatePlan();
  const [created, setCreated] = React.useState<PlanOut | null>(null);

  const form = useForm<CreatePlanFormValues>({
    resolver: zodResolver(createPlanSchema),
    defaultValues: DEFAULT_VALUES,
  });
  const intervalChoice = form.watch("intervalChoice");
  const { errors } = form.formState;

  const onSubmit = form.handleSubmit((values) => {
    mutation.mutate(toPlanIn(values), {
      onSuccess: (plan) => {
        setCreated(plan);
        form.reset(DEFAULT_VALUES);
        toastSuccess("Plan created", `"${plan.name}" is provisioned in Stripe.`);
      },
    });
  });

  const isDuplicate =
    mutation.error instanceof ApiProblem && mutation.error.status === 409;

  return (
    <Card size="sm">
      <CardHeader>
        <CardTitle>Create a plan</CardTitle>
        <CardDescription>
          A plan is a flat access fee plus an optional per-seat fee, provisioned as Stripe Prices.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <form onSubmit={(event) => void onSubmit(event)} className="flex flex-col gap-3" noValidate>
          <FormField
            label="Plan key"
            error={errors.key?.message}
            hint="Your stable identifier for this plan (up to 64 characters, must be unique). Keep a record of it — you'll need it to edit the plan or subscribe customers."
          >
            {(id) => <Input id={id} className="font-mono" placeholder="team-monthly" {...form.register("key")} />}
          </FormField>
          <FormField label="Name" error={errors.name?.message}>
            {(id) => <Input id={id} placeholder="Team" {...form.register("name")} />}
          </FormField>
          <div className="grid gap-3 sm:grid-cols-2">
            <FormField
              label={`Access fee (${currency.toUpperCase()})`}
              error={errors.accessFee?.message}
              hint="Flat recurring fee. Blank = 0."
            >
              {(id) => <Input id={id} inputMode="decimal" placeholder="99" {...form.register("accessFee")} />}
            </FormField>
            <FormField
              label={`Per-seat fee (${currency.toUpperCase()})`}
              error={errors.perSeatFee?.message}
              hint="Charged per live seat. Blank = 0."
            >
              {(id) => <Input id={id} inputMode="decimal" placeholder="15" {...form.register("perSeatFee")} />}
            </FormField>
          </div>
          <FormField label="Billing interval" error={errors.intervalChoice?.message}>
            {(id) => (
              <Controller
                control={form.control}
                name="intervalChoice"
                render={({ field }) => (
                  <Select value={field.value} onValueChange={(value) => field.onChange(value)}>
                    <SelectTrigger id={id} className="w-full" aria-label="Billing interval">
                      <SelectValue>{intervalChoiceText(field.value)}</SelectValue>
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="month">Monthly</SelectItem>
                      <SelectItem value="year">Yearly</SelectItem>
                      <SelectItem value="custom">Custom…</SelectItem>
                    </SelectContent>
                  </Select>
                )}
              />
            )}
          </FormField>
          {intervalChoice === "custom" && (
            <FormField
              label="Custom interval"
              error={errors.customInterval?.message}
              hint="Sent to the API as-is — the contract leaves the interval open beyond monthly and yearly."
            >
              {(id) => <Input id={id} placeholder="week" {...form.register("customInterval")} />}
            </FormField>
          )}

          {mutation.isError && (
            <p className="text-xs text-destructive">
              {isDuplicate
                ? `A plan with this key already exists — keys must be unique. ${problemMessage(mutation.error)}`
                : problemMessage(mutation.error)}
            </p>
          )}
          <div className="flex items-center gap-3">
            <Button type="submit" disabled={mutation.isPending || !isAdmin}>
              {mutation.isPending ? "Working…" : "Create plan"}
            </Button>
            {!isAdmin && (
              <p className="text-xs text-muted-foreground">Creating plans requires the Admin role.</p>
            )}
          </div>
        </form>

        {created && (
          <div className="mt-4 rounded-lg border border-border bg-muted/40 p-3">
            <p className="text-[13px] font-medium text-foreground">Plan created</p>
            <DetailList
              className="mt-1"
              items={[
                {
                  label: "Key",
                  value: (
                    <span className="inline-flex items-center gap-1.5">
                      <span className="font-mono text-[12px]">{created.key}</span>
                      <CopyButton value={created.key} label="Copy plan key" />
                    </span>
                  ),
                },
                { label: "Name", value: created.name },
                { label: "Access fee", value: formatMicros(created.access_fee_micros, currency) },
                { label: "Per-seat fee", value: formatMicros(created.per_seat_micros, currency) },
                { label: "Interval", value: planIntervalLabel(created.interval) },
                { label: "Plan ID", value: created.id, mono: true },
              ]}
            />
            <p className="mt-2 text-xs text-muted-foreground">
              Save the key now — the API can't list plans back later.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
