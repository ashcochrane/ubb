import { useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { X } from "lucide-react";
import { Controller, useForm } from "react-hook-form";

import { problemMessage } from "@/api/problem";
import { ErrorCard } from "@/components/shared/error-card";
import { FormField } from "@/components/shared/form-field";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
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
import { toastSuccess } from "@/lib/mutations";

import { useSaveTenantBudget, useTenantBudget } from "../api/queries";
import type { BudgetConfig } from "../api/types";
import {
  budgetFormSchema,
  budgetFormToPayload,
  budgetToFormValues,
  type BudgetFormValues,
} from "../lib/billing-forms";
import { SectionCard } from "./section-card";

export function BudgetCard() {
  const query = useTenantBudget();
  const isAdmin = useHasRole("admin");

  return (
    <SectionCard
      title="Workspace budget"
      description="A monthly cap on total usage spend across all customers, with alerts on the way up."
    >
      {query.isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-9 w-full max-w-sm" />
          <Skeleton className="h-9 w-full max-w-sm" />
          <Skeleton className="h-9 w-full max-w-sm" />
        </div>
      ) : query.isError ? (
        <ErrorCard error={query.error} onRetry={() => void query.refetch()} />
      ) : query.data ? (
        <BudgetForm initial={query.data} isAdmin={isAdmin} />
      ) : null}
    </SectionCard>
  );
}

function BudgetForm({ initial, isAdmin }: { initial: BudgetConfig; isAdmin: boolean }) {
  const currency = useTenantCurrency();
  const mutation = useSaveTenantBudget();
  const [newLevel, setNewLevel] = useState("");
  const form = useForm<BudgetFormValues>({
    resolver: zodResolver(budgetFormSchema),
    defaultValues: budgetToFormValues(initial),
  });
  const alertLevels = form.watch("alert_levels");

  const addLevel = () => {
    const parsed = Number(newLevel);
    if (!Number.isInteger(parsed) || parsed < 1 || parsed > 1000) return;
    if (!alertLevels.includes(parsed)) {
      form.setValue("alert_levels", [...alertLevels, parsed].sort((a, b) => a - b), {
        shouldDirty: true,
      });
    }
    setNewLevel("");
  };

  const onSubmit = (values: BudgetFormValues) => {
    mutation.mutate(budgetFormToPayload(values), {
      onSuccess: (saved) => {
        toastSuccess("Budget saved");
        form.reset(budgetToFormValues(saved));
      },
    });
  };

  return (
    <form onSubmit={(e) => void form.handleSubmit(onSubmit)(e)} noValidate>
      <fieldset disabled={!isAdmin} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <FormField
          label={`Monthly cap (${currency.toUpperCase()})`}
          error={form.formState.errors.cap?.message}
          hint="Total usage spend allowed per calendar month."
        >
          {(id) => (
            <Input id={id} type="number" min={0} step="0.01" inputMode="decimal" {...form.register("cap")} />
          )}
        </FormField>

        <FormField
          label="When the cap is reached"
          hint="Advisory only sends alerts. Enforcing refuses new work once spending passes the cap."
        >
          {(id) => (
            <Controller
              control={form.control}
              name="enforce_mode"
              render={({ field }) => (
                <Select value={field.value} onValueChange={(v) => field.onChange(v)}>
                  <SelectTrigger id={id} className="w-full" disabled={!isAdmin}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="advisory">Advisory — alert only</SelectItem>
                    <SelectItem value="enforcing">Enforcing — refuse new work</SelectItem>
                  </SelectContent>
                </Select>
              )}
            />
          )}
        </FormField>

        <FormField
          label="Hard stop (% of cap)"
          error={form.formState.errors.hard_stop_pct?.message}
          hint="Spending stops outright at this percentage of the cap — 120 means 120% of the cap. 1–1000."
        >
          {(id) => (
            <Input id={id} type="number" min={1} max={1000} step={1} inputMode="numeric" {...form.register("hard_stop_pct")} />
          )}
        </FormField>

        <FormField
          label="Alert levels (% of cap)"
          hint="Get an alert as spend reaches each percentage of the cap."
        >
          {(id) => (
            <div className="flex flex-wrap items-center gap-1.5">
              {alertLevels.map((level) => (
                <Badge key={level} variant="outline" className="gap-1 pr-1">
                  {level}%
                  {isAdmin && (
                    <button
                      type="button"
                      aria-label={`Remove ${level}% alert`}
                      className="rounded-full p-0.5 hover:bg-bg-subtle"
                      onClick={() =>
                        form.setValue(
                          "alert_levels",
                          alertLevels.filter((l) => l !== level),
                          { shouldDirty: true },
                        )
                      }
                    >
                      <X className="h-3 w-3" />
                    </button>
                  )}
                </Badge>
              ))}
              <Input
                id={id}
                type="number"
                min={1}
                max={1000}
                placeholder="Add %"
                className="h-7 w-20 text-[12px]"
                value={newLevel}
                onChange={(e) => setNewLevel(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    addLevel();
                  }
                }}
              />
              <Button type="button" variant="outline" size="sm" onClick={addLevel}>
                Add
              </Button>
            </div>
          )}
        </FormField>

        <div className="sm:col-span-2">
          <Controller
            control={form.control}
            name="fail_closed"
            render={({ field }) => (
              <label className="flex items-start gap-3">
                <Switch
                  checked={field.value}
                  onCheckedChange={(checked) => field.onChange(checked)}
                  disabled={!isAdmin}
                />
                <span className="text-[13px]">
                  <span className="font-medium text-text-primary">Fail closed</span>
                  <span className="mt-0.5 block text-[12px] text-text-secondary">
                    If UBB can't read the budget state, deny new work instead of allowing it.
                    Safer against overspend, but an internal outage would pause your customers
                    — leave off unless overspending is worse than downtime for you.
                  </span>
                </span>
              </label>
            )}
          />
        </div>
      </fieldset>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <Button type="submit" disabled={!isAdmin || mutation.isPending}>
          {mutation.isPending ? "Working…" : "Save budget"}
        </Button>
        <p className="text-[11px] text-text-muted">
          Saving writes the whole budget — every field above is submitted exactly as shown.
        </p>
      </div>
      {mutation.isError && (
        <p className="mt-2 text-xs text-destructive">{problemMessage(mutation.error)}</p>
      )}
      {!isAdmin && (
        <p className="mt-2 text-[11px] text-text-muted">
          Changing the budget needs the Admin role — you can still review it.
        </p>
      )}
    </form>
  );
}
