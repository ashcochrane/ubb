// Create/edit dialog for a plan's three commercial axes: access fee,
// per-seat fee, and markup. `plan === null` is create mode; otherwise edit.
//
// Schema and conversion helpers live inline (not in a sibling `lib/`
// directory) because this repo's root .gitignore has a bare `lib/` pattern
// that silently swallows ANY directory named `lib` at any depth — that's
// exactly how the pre-existing subscriptions/pricing "lib" helpers went
// missing. Don't reproduce the trap.

import * as React from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { ApiProblem, problemMessage } from "@/api/problem";
import { FormField } from "@/components/shared/form-field";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";

import { useCreatePlan, useUpdatePlan } from "../api/queries";
import type { Plan } from "../api/types";

const decimalString = z
  .string()
  .trim()
  .refine((value) => value === "" || !Number.isNaN(Number(value)), "Enter a number")
  .refine((value) => value === "" || Number(value) >= 0, "Must be zero or more");

const planFormSchema = z.object({
  key: z.string().trim().min(1, "Required").max(64, "Up to 64 characters"),
  name: z.string().trim().min(1, "Required"),
  accessFee: decimalString,
  perSeatFee: decimalString,
  markup: decimalString,
});
type PlanFormValues = z.infer<typeof planFormSchema>;

/** Blank or unparsable -> 0 micros. Money and markup share the same 1e6 scale. */
function toMicros(value: string): number {
  const parsed = Number(value);
  return value.trim() === "" || Number.isNaN(parsed) ? 0 : Math.round(parsed * 1_000_000);
}

/** 0 micros displays as blank — the inverse of "blank means not charged." */
function toFormString(micros: number): string {
  return micros === 0 ? "" : String(micros / 1_000_000);
}

function defaultValues(plan: Plan | null): PlanFormValues {
  if (!plan) {
    return { key: "", name: "", accessFee: "", perSeatFee: "", markup: "" };
  }
  return {
    key: plan.key,
    name: plan.name,
    accessFee: toFormString(plan.access_fee_micros),
    perSeatFee: toFormString(plan.per_seat_micros),
    markup: toFormString(plan.markup_percentage_micros),
  };
}

export function PlanFormDialog({
  open,
  onOpenChange,
  plan,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  plan: Plan | null;
}) {
  const isEdit = plan !== null;
  const create = useCreatePlan();
  const update = useUpdatePlan();
  const mutation = isEdit ? update : create;

  const form = useForm<PlanFormValues>({
    resolver: zodResolver(planFormSchema),
    defaultValues: defaultValues(plan),
  });

  // Re-seed whenever the dialog opens, on whichever plan (or none) it opened for.
  React.useEffect(() => {
    if (open) {
      form.reset(defaultValues(plan));
      create.reset();
      update.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, plan]);

  const onSubmit = form.handleSubmit((values) => {
    if (isEdit) {
      update.mutate(
        {
          key: plan.key,
          input: {
            name: values.name,
            access_fee_micros: toMicros(values.accessFee),
            per_seat_micros: toMicros(values.perSeatFee),
            markup_percentage_micros: toMicros(values.markup),
            migrate_existing: false,
          },
        },
        { onSuccess: () => onOpenChange(false) },
      );
    } else {
      create.mutate(
        {
          key: values.key,
          name: values.name,
          access_fee_micros: toMicros(values.accessFee),
          per_seat_micros: toMicros(values.perSeatFee),
          markup_percentage_micros: toMicros(values.markup),
          fixed_uplift_micros: 0,
          interval: "month",
        },
        { onSuccess: () => onOpenChange(false) },
      );
    }
  });

  const isDuplicateKey =
    !isEdit && create.error instanceof ApiProblem && create.error.status === 409;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{isEdit ? `Edit ${plan.name}` : "Create a plan"}</DialogTitle>
          <DialogDescription>
            {isEdit
              ? "Fee changes create a new Stripe price; existing subscribers keep their " +
                "current one. Markup changes apply immediately."
              : "An access fee, a per-seat fee, and a markup on metered compute — leave any " +
                "axis blank to not charge it."}
          </DialogDescription>
        </DialogHeader>
        <form
          onSubmit={(event) => void onSubmit(event)}
          className="flex flex-col gap-3"
          noValidate
        >
          {!isEdit && (
            <FormField
              label="Plan key"
              error={form.formState.errors.key?.message}
              hint="A stable identifier, unique per workspace."
            >
              {(id) => (
                <Input
                  id={id}
                  className="font-mono"
                  placeholder="enterprise"
                  {...form.register("key")}
                />
              )}
            </FormField>
          )}
          <FormField label="Name" error={form.formState.errors.name?.message}>
            {(id) => <Input id={id} placeholder="Enterprise" {...form.register("name")} />}
          </FormField>
          <div className="grid gap-3 sm:grid-cols-3">
            <FormField
              label="Access fee ($/mo)"
              error={form.formState.errors.accessFee?.message}
              hint="Blank = not charged."
            >
              {(id) => (
                <Input id={id} inputMode="decimal" placeholder="100" {...form.register("accessFee")} />
              )}
            </FormField>
            <FormField
              label="Per-seat fee ($)"
              error={form.formState.errors.perSeatFee?.message}
              hint="Blank = not charged."
            >
              {(id) => (
                <Input id={id} inputMode="decimal" placeholder="10" {...form.register("perSeatFee")} />
              )}
            </FormField>
            <FormField
              label="Markup (%)"
              error={form.formState.errors.markup?.message}
              hint="Blank = no markup."
            >
              {(id) => (
                <Input id={id} inputMode="decimal" placeholder="20" {...form.register("markup")} />
              )}
            </FormField>
          </div>
          {mutation.isError && (
            <p className="text-xs text-destructive">
              {isDuplicateKey
                ? `A plan with this key already exists — keys must be unique. ${problemMessage(mutation.error)}`
                : problemMessage(mutation.error)}
            </p>
          )}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={mutation.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? "Working…" : isEdit ? "Save changes" : "Create plan"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
