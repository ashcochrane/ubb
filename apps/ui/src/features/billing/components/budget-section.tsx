import { Controller, useForm } from "react-hook-form";
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
import {
  ErrorInline,
  LoadingRows,
  Section,
} from "@/components/shared/data-states";
import { FormField } from "@/components/shared/form-field";
import { useBudget, usePutBudget } from "../api/queries";
import {
  budgetSchema,
  parseAlertLevels,
  type BudgetFormValues,
} from "../lib/schema";
import type { BudgetConfig } from "../api/types";

const ENFORCE_MODES: { value: BudgetFormValues["enforceMode"]; label: string }[] =
  [
    { value: "advisory", label: "Advisory — alert only, never block" },
    { value: "monitor", label: "Monitor — track spend, alert at levels" },
    { value: "enforce", label: "Enforce — hard-stop spend over cap" },
  ];

function toForm(b: BudgetConfig): BudgetFormValues {
  return {
    cap: b.cap_micros / 1_000_000,
    enforceMode:
      b.enforce_mode === "monitor" || b.enforce_mode === "enforce"
        ? b.enforce_mode
        : "advisory",
    hardStopPct: b.hard_stop_pct,
    alertLevels: (b.alert_levels ?? []).join(", "),
    failClosed: b.fail_closed,
  };
}

function BudgetForm({ budget }: { budget: BudgetConfig }) {
  const put = usePutBudget();
  const {
    register,
    control,
    handleSubmit,
    formState: { errors },
  } = useForm<BudgetFormValues>({
    resolver: zodResolver(budgetSchema),
    values: toForm(budget),
  });

  const onSubmit = (v: BudgetFormValues) =>
    put.mutate({
      cap_micros: Math.round(v.cap * 1_000_000),
      enforce_mode: v.enforceMode,
      hard_stop_pct: v.hardStopPct,
      alert_levels: parseAlertLevels(v.alertLevels),
      fail_closed: v.failClosed,
    });

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <FormField
          label="Spend cap (USD)"
          error={errors.cap?.message}
          hint="The tenant-wide budget ceiling per period."
        >
          {(id) => (
            <Input
              id={id}
              type="number"
              min={0}
              step={0.01}
              {...register("cap", { valueAsNumber: true })}
            />
          )}
        </FormField>
        <FormField
          label="Enforcement"
          error={errors.enforceMode?.message}
          hint="Controls whether overspend is blocked or merely alerted."
        >
          {(id) => (
            <Controller
              control={control}
              name="enforceMode"
              render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger id={id} className="w-full">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {ENFORCE_MODES.map((m) => (
                      <SelectItem key={m.value} value={m.value}>
                        {m.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            />
          )}
        </FormField>
        <FormField
          label="Hard-stop at (% of cap)"
          error={errors.hardStopPct?.message}
          hint="Under Enforce, block spend once this % of the cap is reached."
        >
          {(id) => (
            <Input
              id={id}
              type="number"
              min={0}
              max={1000}
              step={1}
              {...register("hardStopPct", { valueAsNumber: true })}
            />
          )}
        </FormField>
        <FormField
          label="Alert levels (%)"
          error={errors.alertLevels?.message}
          hint="Comma-separated, e.g. 50, 80, 100."
        >
          {(id) => <Input id={id} placeholder="50, 80, 100" {...register("alertLevels")} />}
        </FormField>
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          className="size-4 accent-foreground"
          {...register("failClosed")}
        />
        Fail closed — if budget state can't be read, block spend rather than allow it
      </label>
      <Button type="submit" disabled={put.isPending}>
        {put.isPending ? "Saving…" : "Save budget"}
      </Button>
    </form>
  );
}

export function BudgetSection() {
  const query = useBudget();
  return (
    <Section
      title="Tenant budget"
      description="A tenant-wide spend cap with alerting and optional hard enforcement."
    >
      {query.isLoading ? (
        <LoadingRows rows={3} />
      ) : query.isError ? (
        <ErrorInline error={query.error} onRetry={() => query.refetch()} />
      ) : query.data ? (
        <BudgetForm budget={query.data} />
      ) : null}
    </Section>
  );
}
