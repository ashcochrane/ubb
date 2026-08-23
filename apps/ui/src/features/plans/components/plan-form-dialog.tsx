// Create/edit dialog for a plan's two fee axes: access fee and per-seat fee.
// `plan === null` is create mode; otherwise edit.
//
// ⚠ THERE IS NO MARKUP FIELD (#369). A plan carried a markup percentage and a
// per-event flat amount, and both columns are deleted. What a plan's customers
// pay for usage is the rules in the pricing book the plan names, changed
// through a publish on that book — which is what gives a tenant a diff to read
// before a price moves. The console gained that surface in #372: the book's own
// page declares a change, shows its diff, and publishes or discards it.
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
});
type PlanFormValues = z.infer<typeof planFormSchema>;

/** Blank or unparsable -> 0 micros. */
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
    return { key: "", name: "", accessFee: "", perSeatFee: "" };
  }
  return {
    key: plan.key,
    name: plan.name,
    accessFee: toFormString(plan.access_fee_micros),
    perSeatFee: toFormString(plan.per_seat_micros),
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
                "current one. What this plan's customers pay for usage lives in the " +
                "pricing book it prices from, not here."
              : "An access fee and a per-seat fee — leave either blank to not charge it. " +
                "Usage is priced from the pricing book created with the plan."}
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
          <div className="grid gap-3 sm:grid-cols-2">
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
