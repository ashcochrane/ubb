// Customer budget: live status meter + config form. The PUT is a FULL upsert
// with schema defaults, so the form is prefilled from GET and every field is
// always sent on save.

import * as React from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { toast } from "sonner";

import { problemMessage } from "@/api/problem";
import { ErrorCard } from "@/components/shared/error-card";
import { FormField } from "@/components/shared/form-field";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { useHasRole } from "@/hooks/use-current-role";
import { useTenantCurrency } from "@/hooks/use-tenant-config";
import { formatMicros, formatPercent } from "@/lib/format";
import { budgetEnforceModeLabel } from "@/lib/labels";
import { cn } from "@/lib/utils";

import { useBudgetStatus, useCustomerBudget, useSaveBudget } from "../api/queries";
import {
  formatAlertLevels,
  microsToUnits,
  parseAlertLevels,
  toMicros,
} from "../lib/helpers";
import { budgetSchema, type BudgetForm } from "../lib/schemas";

export function BudgetSection({ customerId }: { customerId: string }) {
  const currency = useTenantCurrency();
  const isAdmin = useHasRole("admin");
  const budget = useCustomerBudget(customerId);
  const status = useBudgetStatus(customerId);
  const mutation = useSaveBudget(customerId);

  const form = useForm<BudgetForm>({
    resolver: zodResolver(budgetSchema),
    defaultValues: {
      cap: "",
      enforce_mode: "alert_only",
      hard_stop_pct: "100",
      alert_levels: "",
      fail_closed: false,
    },
  });

  const config = budget.data;
  React.useEffect(() => {
    if (config) {
      form.reset({
        cap: microsToUnits(config.cap_micros),
        enforce_mode: config.enforce_mode,
        hard_stop_pct: String(config.hard_stop_pct),
        alert_levels: formatAlertLevels(config.alert_levels),
        fail_closed: config.fail_closed,
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [config]);

  const submit = form.handleSubmit(async (values) => {
    try {
      await mutation.mutateAsync({
        cap_micros: toMicros(values.cap),
        enforce_mode: values.enforce_mode,
        hard_stop_pct: Number(values.hard_stop_pct),
        alert_levels: parseAlertLevels(values.alert_levels),
        fail_closed: values.fail_closed,
      });
      toast.success("Budget saved");
    } catch {
      // surfaced below
    }
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Monthly budget</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {status.isLoading ? (
          <Skeleton className="h-10 w-full" />
        ) : status.isError ? (
          <ErrorCard error={status.error} onRetry={() => void status.refetch()} />
        ) : status.data && status.data.cap_micros > 0 ? (
          <div className="space-y-1.5">
            <div className="flex items-baseline justify-between text-[12px]">
              <span className="text-text-secondary">
                {status.data.period} — {formatMicros(status.data.spend_micros, currency)}{" "}
                of {formatMicros(status.data.cap_micros, currency)} (
                {budgetEnforceModeLabel(status.data.enforce_mode)})
              </span>
              <span
                className={cn(
                  "font-medium tabular-nums",
                  status.data.pct >= 100 && "text-danger-dark",
                )}
              >
                {formatPercent(status.data.pct)}
              </span>
            </div>
            <div
              className="h-2 overflow-hidden rounded-full bg-bg-subtle"
              role="meter"
              aria-valuemin={0}
              aria-valuemax={100}
              aria-valuenow={Math.min(Math.round(status.data.pct), 100)}
              aria-label="Budget consumed"
            >
              <div
                className={cn(
                  "h-full rounded-full",
                  status.data.pct >= 100 ? "bg-red" : "bg-accent-base",
                )}
                style={{ width: `${Math.min(status.data.pct, 100)}%` }}
              />
            </div>
          </div>
        ) : (
          <p className="text-[12px] text-text-muted">
            No budget cap set — spending is not measured against a monthly cap yet.
          </p>
        )}

        {budget.isLoading ? (
          <Skeleton className="h-40 w-full" />
        ) : budget.isError ? (
          <ErrorCard error={budget.error} onRetry={() => void budget.refetch()} />
        ) : (
          <form onSubmit={(event) => void submit(event)} className="space-y-2.5">
            <p className="text-[11px] text-text-muted">
              Saving writes the whole budget config exactly as shown — fields left
              at defaults are saved as defaults, not preserved.
            </p>
            <div className="grid grid-cols-2 gap-2.5">
              <FormField
                label={`Monthly cap (${currency.toUpperCase()})`}
                error={form.formState.errors.cap?.message}
              >
                {(id) => <Input id={id} inputMode="decimal" {...form.register("cap")} />}
              </FormField>
              <FormField
                label="Mode"
                hint="Advisory alerts only; Enforcing can stop spend at the cap."
              >
                {() => (
                  <Select
                    value={form.watch("enforce_mode")}
                    onValueChange={(value) =>
                      form.setValue("enforce_mode", value ?? "alert_only")
                    }
                  >
                    <SelectTrigger className="w-full" aria-label="Enforce mode">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="alert_only">Alert only</SelectItem>
                      <SelectItem value="blocking">Blocking</SelectItem>
                    </SelectContent>
                  </Select>
                )}
              </FormField>
            </div>
            <div className="grid grid-cols-2 gap-2.5">
              <FormField
                label="Hard stop at (% of cap)"
                error={form.formState.errors.hard_stop_pct?.message}
                hint="1–1000. 100 = stop exactly at the cap."
              >
                {(id) => (
                  <Input id={id} inputMode="numeric" {...form.register("hard_stop_pct")} />
                )}
              </FormField>
              <FormField
                label="Alert levels (%)"
                hint="Comma-separated, e.g. 50, 80, 100."
              >
                {(id) => <Input id={id} {...form.register("alert_levels")} />}
              </FormField>
            </div>
            <div className="flex items-center gap-2">
              <Switch
                id="budget-fail-closed"
                checked={form.watch("fail_closed")}
                onCheckedChange={(checked) => form.setValue("fail_closed", checked)}
              />
              <Label htmlFor="budget-fail-closed">
                Fail closed — deny spending when the budget state can't be read
              </Label>
            </div>
            {mutation.error != null && (
              <p className="text-[12px] text-danger-dark" role="alert">
                {problemMessage(mutation.error)}
              </p>
            )}
            <div className="flex items-center gap-2">
              <Button type="submit" size="sm" disabled={mutation.isPending || !isAdmin}>
                {mutation.isPending ? "Working…" : "Save budget"}
              </Button>
              {!isAdmin && (
                <span className="text-[11px] text-text-muted">
                  Requires the Admin role.
                </span>
              )}
            </div>
          </form>
        )}
      </CardContent>
    </Card>
  );
}
