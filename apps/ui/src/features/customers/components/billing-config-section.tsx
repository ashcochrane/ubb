// Billing profile (spend floors + top-up grant expiry) and auto top-up.
//
// Floor wire semantics (spec-billing-margin §2.7/2.8 + tenant config):
// min_balance_micros is the ALLOWED OVERDRAFT MAGNITUDE (≥ 0 — the stop line
// sits at MINUS the value; the server 422s negatives), and the wind-down
// soft_min_balance_micros is likewise negated on the wire (a negative wire
// value places the wind-down line ABOVE zero). The inputs here take the raw
// wire value, so the copy explains that orientation.
//
// Auto top-up has NO read endpoint — the form starts blank and always
// overwrites, which the copy says out loud.

import * as React from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { Info } from "lucide-react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";
import { Link } from "@tanstack/react-router";

import { problemMessage } from "@/api/problem";
import { DetailList } from "@/components/shared/detail-list";
import { ErrorCard } from "@/components/shared/error-card";
import { FormField } from "@/components/shared/form-field";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { useHasRole } from "@/hooks/use-current-role";
import { useIsPostpaid, useTenantCurrency } from "@/hooks/use-tenant-config";
import { formatMicros } from "@/lib/format";

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
  const postpaid = useIsPostpaid();
  const query = useBillingProfile(customerId, !postpaid);
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
        {postpaid ? (
          <Alert>
            <Info />
            <AlertDescription>
              Overdraft and wind-down floors aren't used under postpaid
              billing — usage drawdown skips the wallet entirely, so there's
              no balance floor to configure here. The monthly budget below is
              the live spend control instead.
            </AlertDescription>
          </Alert>
        ) : query.isLoading ? (
          <Skeleton className="h-40 w-full" />
        ) : query.isError ? (
          <ErrorCard error={query.error} onRetry={() => void query.refetch()} />
        ) : profile?.is_pooled_seat ? (
          <div className="space-y-3">
            <Alert>
              <Info />
              <AlertDescription>
                This seat has no wallet of its own — spend floors are set on
                the billing owner,{" "}
                <Link
                  to="/customers/$customerId"
                  params={{ customerId: profile.billing_owner_id }}
                  className="font-medium underline-offset-2 hover:underline"
                >
                  {profile.billing_owner_external_id}
                </Link>
                . Edit them there — the API refuses (422) writing floors to a
                pooled seat's own profile.
              </AlertDescription>
            </Alert>
            <DetailList
              items={[
                {
                  label: `Allowed overdraft (${currency})`,
                  value:
                    profile.min_balance_micros != null
                      ? formatMicros(profile.min_balance_micros, currency)
                      : "Inherits the workspace default",
                },
                {
                  label: `Wind-down floor (${currency})`,
                  value:
                    profile.soft_min_balance_micros != null
                      ? formatMicros(profile.soft_min_balance_micros, currency)
                      : "Inherits the workspace default",
                },
                {
                  label: "Top-up credit expires after",
                  value:
                    profile.topup_grant_expiry_days != null
                      ? `${profile.topup_grant_expiry_days} days`
                      : "Never",
                },
              ]}
            />
          </div>
        ) : (
          <form onSubmit={(event) => void submit(event)} className="space-y-2.5">
            <FormField
              label={`Allowed overdraft (${currency})`}
              error={form.formState.errors.min_balance?.message}
              hint="How far past zero this customer may spend before the customer-wide stop fires: 0 = stop at zero, 50 = stop once the balance falls below −50. Zero or more. Blank = inherit the workspace default."
            >
              {(id) => (
                <Input id={id} inputMode="decimal" {...form.register("min_balance")} />
              )}
            </FormField>
            <FormField
              label={`Wind-down floor (${currency}, depth into the overdraft)`}
              error={form.formState.errors.soft_min_balance?.message}
              hint="How deep into the overdraft NEW tasks start being refused while running work finishes: 20 = wind down once the balance falls below −20; a negative value (−50) winds down early, while the balance is still at 50. Can't exceed the allowed overdraft. Blank = inherit the workspace default."
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
  const postpaid = useIsPostpaid();
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

  if (postpaid) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Auto top-up</CardTitle>
        </CardHeader>
        <CardContent>
          <Alert>
            <Info />
            <AlertDescription>
              Auto top-up isn't used under postpaid billing — there's no
              prepaid wallet to top up. Usage is invoiced through Stripe at
              period close instead.
            </AlertDescription>
          </Alert>
        </CardContent>
      </Card>
    );
  }

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
