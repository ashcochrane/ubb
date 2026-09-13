// The workspace's Customer Spend Pool default on the Billing page (#468;
// slice 6 §4, §18): the pool for every seat that declares none of its own,
// and for no business — the card says whose it is in words, because one
// configured number must never be read as a line at two altitudes.
//
// The declaration is the only thing here. A default has no pair of its own
// to read: where one customer's known charges stand against it is that
// customer's Billing tab's, and the pool's alert levels announce themselves
// through the webhook catalogue rather than through anything this card
// draws. The mode is the registry's closed pair held by reference, worded by
// the catalogue through `@/lib/spend-pool`.

import { useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { X } from "lucide-react";
import { Controller, useForm } from "react-hook-form";

import { problemMessage } from "@/api/problem";
import { DisabledHint } from "@/components/shared/disabled-hint";
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
import { SEAT_DEFAULT_LEVEL, SPEND_POOL_ENFORCE_MODE_WORDS } from "@/lib/spend-pool";
import { SPEND_POOL_ENFORCE_MODE_VALUES } from "@/lib/vocabulary";

import { useSaveTenantCustomerSpendPool, useTenantCustomerSpendPool } from "../api/queries";
import type { CustomerSpendPool } from "../api/types";
import {
  customerSpendPoolFormSchema,
  customerSpendPoolFormToPayload,
  customerSpendPoolToFormValues,
  type CustomerSpendPoolFormValues,
} from "../lib/customer-spend-pool-form";
import { SectionCard } from "./section-card";

export const SEAT_DEFAULT_POOL_TITLE = "Customer spend pool default";

export function CustomerSpendPoolCard() {
  const query = useTenantCustomerSpendPool();
  const isAdmin = useHasRole("admin");

  return (
    <SectionCard title={SEAT_DEFAULT_POOL_TITLE} description={SEAT_DEFAULT_LEVEL}>
      {query.isLoading ? (
        <div className="space-y-3">
          <Skeleton className="h-9 w-full max-w-sm" />
          <Skeleton className="h-9 w-full max-w-sm" />
          <Skeleton className="h-9 w-full max-w-sm" />
        </div>
      ) : query.isError ? (
        <ErrorCard error={query.error} onRetry={() => void query.refetch()} />
      ) : query.data ? (
        <SeatDefaultPoolForm initial={query.data} isAdmin={isAdmin} />
      ) : null}
    </SectionCard>
  );
}

function SeatDefaultPoolForm({
  initial,
  isAdmin,
}: {
  initial: CustomerSpendPool;
  isAdmin: boolean;
}) {
  const currency = useTenantCurrency();
  const mutation = useSaveTenantCustomerSpendPool();
  const [newLevel, setNewLevel] = useState("");
  const form = useForm<CustomerSpendPoolFormValues>({
    resolver: zodResolver(customerSpendPoolFormSchema),
    defaultValues: customerSpendPoolToFormValues(initial),
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

  const onSubmit = (values: CustomerSpendPoolFormValues) => {
    mutation.mutate(customerSpendPoolFormToPayload(values), {
      onSuccess: (saved) => {
        toastSuccess("Customer spend pool default saved");
        form.reset(customerSpendPoolToFormValues(saved));
      },
    });
  };

  return (
    <form onSubmit={(e) => void form.handleSubmit(onSubmit)(e)} noValidate>
      <fieldset disabled={!isAdmin} className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <FormField
          label={`Monthly cap (${currency.toUpperCase()})`}
          error={form.formState.errors.cap?.message}
          hint="The charges one seat may accrue per calendar month. An amount of nothing declares no default."
        >
          {(id) => (
            <Input id={id} type="number" min={0} step="0.01" inputMode="decimal" {...form.register("cap")} />
          )}
        </FormField>

        <FormField
          label="Mode"
          hint="Alert only announces each level reached. Blocking also refuses new starts and stops active work at the stop line."
        >
          {(id) => (
            <Controller
              control={form.control}
              name="enforce_mode"
              render={({ field }) => (
                <Select
                  value={field.value}
                  items={SPEND_POOL_ENFORCE_MODE_WORDS}
                  onValueChange={(v) => field.onChange(v)}
                >
                  <SelectTrigger id={id} className="w-full" disabled={!isAdmin}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {SPEND_POOL_ENFORCE_MODE_VALUES.map((mode) => (
                      <SelectItem key={mode} value={mode}>
                        {SPEND_POOL_ENFORCE_MODE_WORDS[mode]}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            />
          )}
        </FormField>

        <FormField
          label="Stop line (% of cap)"
          error={form.formState.errors.hard_stop_pct?.message}
          hint="Where a blocking pool stops, as a percentage of the cap — 120 means 120% of it. 1–1000."
        >
          {(id) => (
            <Input id={id} type="number" min={1} max={1000} step={1} inputMode="numeric" {...form.register("hard_stop_pct")} />
          )}
        </FormField>

        <FormField
          label="Alert levels (% of cap)"
          hint="Announced as the known charges reach each percentage of the cap."
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
                    If UBB can't read where a seat's charges stand against the pool,
                    refuse new starts instead of allowing them. Safer against
                    overspend, but an internal outage would pause your customers
                    — leave off unless overspending is worse than downtime for you.
                  </span>
                </span>
              </label>
            )}
          />
        </div>
      </fieldset>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <DisabledHint disabled={!isAdmin} hint="Requires the Admin role.">
          <Button type="submit" disabled={!isAdmin || mutation.isPending}>
            {mutation.isPending ? "Working…" : "Save default pool"}
          </Button>
        </DisabledHint>
        <p className="text-[11px] text-text-muted">
          Saving writes the whole declaration — every field above is submitted exactly as shown.
        </p>
      </div>
      {mutation.isError && (
        <p className="mt-2 text-xs text-destructive">{problemMessage(mutation.error)}</p>
      )}
      {!isAdmin && (
        <p className="mt-2 text-[11px] text-text-muted">
          Changing the default needs the Admin role — you can still review it.
        </p>
      )}
    </form>
  );
}
