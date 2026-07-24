// Billing profile (balance floors + top-up grant expiry) and auto top-up.
// Auto top-up has NO read endpoint — the form starts blank and always
// overwrites, which the copy says out loud.

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
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { useHasRole } from "@/hooks/use-current-role";
import { useTenantCurrency } from "@/hooks/use-tenant-config";

import {
  useBillingProfile,
  useConfigureAutoTopUp,
  useSaveBillingProfile,
} from "../api/queries";
import { microsToUnits, toMicros } from "../lib/helpers";
import {
  autoTopUpSchema,
  billingProfileSchema,
  type AutoTopUpForm,
  type BillingProfileForm,
} from "../lib/schemas";

const ADMIN_HINT = "Requires the Admin role.";

export function BillingConfigSection({ customerId }: { customerId: string }) {
  return (
    <div className="grid gap-3 lg:grid-cols-2">
      <BillingProfileCard customerId={customerId} />
      <AutoTopUpCard customerId={customerId} />
    </div>
  );
}

function BillingProfileCard({ customerId }: { customerId: string }) {
  const currency = useTenantCurrency().toUpperCase();
  const isAdmin = useHasRole("admin");
  const query = useBillingProfile(customerId);
  const mutation = useSaveBillingProfile(customerId);
  const form = useForm<BillingProfileForm>({
    resolver: zodResolver(billingProfileSchema),
    defaultValues: { min_balance: "", soft_min_balance: "", topup_grant_expiry_days: "" },
  });

  const profile = query.data;
  React.useEffect(() => {
    if (profile) {
      form.reset({
        min_balance:
          profile.min_balance_micros != null
            ? microsToUnits(profile.min_balance_micros)
            : "",
        soft_min_balance:
          profile.soft_min_balance_micros != null
            ? microsToUnits(profile.soft_min_balance_micros)
            : "",
        topup_grant_expiry_days:
          profile.topup_grant_expiry_days != null
            ? String(profile.topup_grant_expiry_days)
            : "",
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [profile]);

  const submit = form.handleSubmit(async (values) => {
    try {
      await mutation.mutateAsync({
        min_balance_micros:
          values.min_balance === "" ? null : toMicros(values.min_balance),
        soft_min_balance_micros:
          values.soft_min_balance === "" ? null : toMicros(values.soft_min_balance),
        topup_grant_expiry_days:
          values.topup_grant_expiry_days === ""
            ? null
            : Number(values.topup_grant_expiry_days),
      });
      toast.success("Billing profile saved");
    } catch {
      // surfaced below
    }
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Billing profile</CardTitle>
      </CardHeader>
      <CardContent>
        {query.isLoading ? (
          <Skeleton className="h-40 w-full" />
        ) : query.isError ? (
          <ErrorCard error={query.error} onRetry={() => void query.refetch()} />
        ) : (
          <form onSubmit={(event) => void submit(event)} className="space-y-2.5">
            <FormField
              label={`Balance floor (${currency})`}
              error={form.formState.errors.min_balance?.message}
              hint="Spending stops when the balance falls below this floor. Blank = inherit the workspace default. Negative values allow a controlled overdraft."
            >
              {(id) => (
                <Input id={id} inputMode="decimal" {...form.register("min_balance")} />
              )}
            </FormField>
            <FormField
              label={`Soft floor (${currency})`}
              error={form.formState.errors.soft_min_balance?.message}
              hint="Below this level, NEW tasks are refused but running work finishes. Must sit at or above the balance floor. Blank = none."
            >
              {(id) => (
                <Input
                  id={id}
                  inputMode="decimal"
                  {...form.register("soft_min_balance")}
                />
              )}
            </FormField>
            <FormField
              label="Top-up credit expires after (days)"
              error={form.formState.errors.topup_grant_expiry_days?.message}
              hint="Credit bought via top-up expires this many days after purchase. Blank = never expires."
            >
              {(id) => (
                <Input
                  id={id}
                  inputMode="numeric"
                  {...form.register("topup_grant_expiry_days")}
                />
              )}
            </FormField>
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
        )}
      </CardContent>
    </Card>
  );
}

function AutoTopUpCard({ customerId }: { customerId: string }) {
  const currency = useTenantCurrency().toUpperCase();
  const isAdmin = useHasRole("admin");
  const mutation = useConfigureAutoTopUp(customerId);
  const form = useForm<AutoTopUpForm>({
    resolver: zodResolver(autoTopUpSchema),
    defaultValues: { is_enabled: true, amount: "", threshold: "" },
  });

  const submit = form.handleSubmit(async (values) => {
    try {
      await mutation.mutateAsync({
        is_enabled: values.is_enabled,
        top_up_amount_micros: toMicros(values.amount),
        trigger_threshold_micros: toMicros(values.threshold),
      });
      toast.success("Auto top-up settings saved");
    } catch {
      // surfaced below
    }
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Auto top-up</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={(event) => void submit(event)} className="space-y-2.5">
          <p className="text-[11px] text-text-muted">
            Current settings can't be read back — the API has no read endpoint for
            auto top-up, so this form starts blank and saving always overwrites
            whatever is configured.
          </p>
          <div className="flex items-center gap-2">
            <Switch
              id="auto-top-up-enabled"
              checked={form.watch("is_enabled")}
              onCheckedChange={(checked) => form.setValue("is_enabled", checked)}
            />
            <Label htmlFor="auto-top-up-enabled">Auto top-up enabled</Label>
          </div>
          <div className="grid grid-cols-2 gap-2.5">
            <FormField
              label={`Top-up amount (${currency})`}
              error={form.formState.errors.amount?.message}
              hint="Charged via the saved payment method each time it triggers."
            >
              {(id) => <Input id={id} inputMode="decimal" {...form.register("amount")} />}
            </FormField>
            <FormField
              label={`Trigger below (${currency})`}
              error={form.formState.errors.threshold?.message}
              hint="Fires when the balance drops under this level."
            >
              {(id) => (
                <Input id={id} inputMode="decimal" {...form.register("threshold")} />
              )}
            </FormField>
          </div>
          {mutation.error != null && (
            <p className="text-[12px] text-danger-dark" role="alert">
              {problemMessage(mutation.error)}
            </p>
          )}
          <div className="flex items-center gap-2">
            <Button type="submit" size="sm" disabled={mutation.isPending || !isAdmin}>
              {mutation.isPending ? "Working…" : "Save auto top-up"}
            </Button>
            {!isAdmin && <span className="text-[11px] text-text-muted">{ADMIN_HINT}</span>}
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
