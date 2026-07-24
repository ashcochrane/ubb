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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { useHasRole } from "@/hooks/use-current-role";
import { useTenantCurrency } from "@/hooks/use-tenant-config";
import { formatMicros, formatShortDate } from "@/lib/format";
import { humanize, revenueModeLabel } from "@/lib/labels";

import {
  useRevenueMode,
  useRevenueProfile,
  useSaveRevenueMode,
  useSaveRevenueProfile,
} from "../api/queries";
import { microsToUnits, toMicros } from "../lib/helpers";
import { revenueProfileSchema, type RevenueProfileForm } from "../lib/schemas";

const ADMIN_HINT = "Requires the Admin role.";

export function RevenuePanels({ customerId }: { customerId: string }) {
  return (
    <div className="grid gap-3 lg:grid-cols-2">
      <RevenueProfileCard customerId={customerId} />
      <RevenueModeCard customerId={customerId} />
    </div>
  );
}

function RevenueProfileCard({ customerId }: { customerId: string }) {
  const currency = useTenantCurrency();
  const isAdmin = useHasRole("admin");
  const query = useRevenueProfile(customerId);
  const mutation = useSaveRevenueProfile(customerId);
  const form = useForm<RevenueProfileForm>({
    resolver: zodResolver(revenueProfileSchema),
    defaultValues: { amount: "", interval: "month", effective_from: "", effective_to: "" },
  });

  const profile = query.data ?? null;
  React.useEffect(() => {
    if (profile) {
      form.reset({
        amount: microsToUnits(profile.recurring_amount_micros),
        interval: profile.interval,
        effective_from: profile.effective_from.slice(0, 10),
        effective_to: profile.effective_to ? profile.effective_to.slice(0, 10) : "",
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profile]);

  const submit = form.handleSubmit(async (values) => {
    try {
      await mutation.mutateAsync({
        recurring_amount_micros: toMicros(values.amount),
        currency,
        interval: values.interval,
        effective_from: values.effective_from || null,
        effective_to: values.effective_to || null,
      });
      toast.success("Recurring revenue profile saved");
    } catch {
      // surfaced below
    }
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Recurring revenue</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {query.isLoading ? (
          <Skeleton className="h-32 w-full" />
        ) : query.isError ? (
          <ErrorCard error={query.error} onRetry={() => void query.refetch()} />
        ) : (
          <>
            <p className="text-[12px] text-text-secondary">
              {profile
                ? `Currently ${formatMicros(profile.recurring_amount_micros, profile.currency)} per ${humanize(profile.interval).toLowerCase()}, effective ${formatShortDate(profile.effective_from)}${profile.effective_to ? ` → ${formatShortDate(profile.effective_to)}` : " (open-ended)"}.`
                : "No recurring revenue profile yet. Set one when this customer pays a flat recurring amount outside a Stripe subscription — it accrues into margin month-prorated."}
            </p>
            <form onSubmit={(event) => void submit(event)} className="space-y-2.5">
              <div className="grid grid-cols-2 gap-2.5">
                <FormField
                  label={`Amount (${currency.toUpperCase()})`}
                  error={form.formState.errors.amount?.message}
                >
                  {(id) => (
                    <Input id={id} inputMode="decimal" {...form.register("amount")} placeholder="199" />
                  )}
                </FormField>
                <FormField label="Interval">
                  {() => (
                    <Select
                      value={form.watch("interval")}
                      onValueChange={(value) =>
                        form.setValue("interval", value ?? "month")
                      }
                    >
                      <SelectTrigger className="w-full" aria-label="Interval">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="month">Monthly</SelectItem>
                        <SelectItem value="year">Yearly</SelectItem>
                      </SelectContent>
                    </Select>
                  )}
                </FormField>
              </div>
              <div className="grid grid-cols-2 gap-2.5">
                <FormField label="Effective from" hint="Blank = now.">
                  {(id) => <Input id={id} type="date" {...form.register("effective_from")} />}
                </FormField>
                <FormField label="Effective to" hint="Blank = open-ended.">
                  {(id) => <Input id={id} type="date" {...form.register("effective_to")} />}
                </FormField>
              </div>
              {mutation.error != null && (
                <p className="text-[12px] text-danger-dark" role="alert">
                  {problemMessage(mutation.error)}
                </p>
              )}
              <div className="flex items-center gap-2">
                <Button type="submit" size="sm" disabled={mutation.isPending || !isAdmin}>
                  {mutation.isPending ? "Working…" : "Save profile"}
                </Button>
                {!isAdmin && <span className="text-[11px] text-text-muted">{ADMIN_HINT}</span>}
              </div>
            </form>
          </>
        )}
      </CardContent>
    </Card>
  );
}

const MODE_OPTIONS = [
  {
    value: "inherit",
    label: "Inherit workspace default",
    explanation:
      "No override — meter-only workspaces resolve to metered only; billing workspaces resolve to billed.",
  },
  {
    value: "billed",
    label: "Billed",
    explanation:
      "Billed usage counts as revenue for this customer, so margin = revenue − provider cost.",
  },
  {
    value: "metered_only",
    label: "Metered only",
    explanation:
      "Usage is tracked but billed amounts do NOT count as revenue — margin shows only the cost of serving this customer (plus any subscription or recurring revenue).",
  },
];

function RevenueModeCard({ customerId }: { customerId: string }) {
  const isAdmin = useHasRole("admin");
  const query = useRevenueMode(customerId);
  const mutation = useSaveRevenueMode(customerId);
  const [selected, setSelected] = React.useState<string | null>(null);

  const stored = query.data?.revenue_mode ?? "";
  const value = selected ?? (stored === "" ? "inherit" : stored);
  const explanation = MODE_OPTIONS.find((option) => option.value === value)?.explanation;

  const save = async () => {
    try {
      await mutation.mutateAsync(value === "inherit" ? "" : value);
      setSelected(null);
      toast.success("Revenue mode saved");
    } catch {
      // surfaced below (422 invalid_revenue_mode included)
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Revenue mode</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {query.isLoading ? (
          <Skeleton className="h-32 w-full" />
        ) : query.isError ? (
          <ErrorCard error={query.error} onRetry={() => void query.refetch()} />
        ) : (
          <>
            <p className="text-[12px] text-text-secondary">
              Controls whether billed usage counts as revenue in this customer's
              margin math. Resolved right now:{" "}
              <span className="font-medium text-text-primary">
                {revenueModeLabel(query.data?.resolved)}
              </span>
              .
            </p>
            <Select value={value} onValueChange={setSelected}>
              <SelectTrigger className="w-full" aria-label="Revenue mode">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {MODE_OPTIONS.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {explanation && <p className="text-[11px] text-text-muted">{explanation}</p>}
            {mutation.error != null && (
              <p className="text-[12px] text-danger-dark" role="alert">
                {problemMessage(mutation.error)}
              </p>
            )}
            <div className="flex items-center gap-2">
              <Button
                size="sm"
                onClick={() => void save()}
                disabled={mutation.isPending || !isAdmin || selected === null}
              >
                {mutation.isPending ? "Working…" : "Save mode"}
              </Button>
              {!isAdmin && <span className="text-[11px] text-text-muted">{ADMIN_HINT}</span>}
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
