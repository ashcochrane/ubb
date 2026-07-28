import { useForm, Controller, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Info } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from "@/components/ui/select";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { FormField } from "@/components/shared/form-field";
import { Section, DetailGrid, DetailRow } from "@/components/shared/data-states";
import { BoolBadge, StatusBadge } from "@/components/shared/status-badge";
import { CheckboxRow } from "./checkbox-row";
import { useUpdateConfig } from "../api/queries";
import {
  generalSettingsSchema,
  dollarsToMicros,
  microsToDollars,
  type GeneralSettingsValues,
} from "../lib/schema";
import type { TenantConfig } from "../api/types";

const BILLING_MODES = [
  { value: "meter_only", label: "Meter only" },
  { value: "prepaid", label: "Prepaid" },
  { value: "postpaid", label: "Postpaid" },
] as const;

// Tenant.enforcement_mode has exactly two real values (#42, spec §G):
// "off" and "enforcing". There is no "monitor" — every route reads this via
// apps.platform.tenants.flags.enforcing(), which treats anything but
// "enforcing" as off, so offering a third value here would silently leave
// the tenant unenforced while the operator believes they configured it.
const ENFORCEMENT_MODES = [
  { value: "off", label: "Off" },
  { value: "enforcing", label: "Enforcing" },
] as const;

export function GeneralTab({ config }: { config: TenantConfig }) {
  const update = useUpdateConfig();

  const form = useForm<GeneralSettingsValues>({
    resolver: zodResolver(generalSettingsSchema),
    defaultValues: toDefaults(config),
  });
  const { errors } = form.formState;
  // Live-tracks the billing-mode field (not just the saved config) so the
  // floor fields react immediately if the operator switches to postpaid in
  // this same form, before saving.
  const isPostpaid = useWatch({ control: form.control, name: "billing_mode" }) === "postpaid";

  const onSubmit = form.handleSubmit(async (values) => {
    await update.mutateAsync({
      billing_mode: values.billing_mode,
      default_currency: values.default_currency.toUpperCase(),
      enforcement_mode: values.enforcement_mode,
      min_balance_micros: dollarsToMicros(values.min_balance_micros) ?? 0,
      soft_min_balance_micros: dollarsToMicros(values.soft_min_balance_micros),
      default_task_provider_cost_limit_micros: dollarsToMicros(
        values.default_task_provider_cost_limit_micros,
      ),
      require_cost_card_coverage: values.require_cost_card_coverage,
      automatic_tax_enabled: values.automatic_tax_enabled,
      arrival_signals_enabled: values.arrival_signals_enabled,
    });
  });

  return (
    <div className="space-y-6">
      <Section title="Identity" description="Read-only values managed elsewhere.">
        <DetailGrid>
          <DetailRow label="Tenant name">{config.name}</DetailRow>
          <DetailRow label="Active">
            <BoolBadge value={config.is_active} />
          </DetailRow>
          <DetailRow label="Stripe connected account">
            {config.stripe_connected_account_id ? (
              <span className="font-mono text-xs break-all">
                {config.stripe_connected_account_id}
              </span>
            ) : (
              <StatusBadge value="Not connected" tone="muted" />
            )}
          </DetailRow>
        </DetailGrid>
      </Section>

      <form onSubmit={onSubmit}>
        <Section
          title="Billing & enforcement"
          actions={
            <Button type="submit" size="sm" disabled={update.isPending}>
              {update.isPending ? "Saving…" : "Save changes"}
            </Button>
          }
        >
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <FormField label="Billing mode" error={errors.billing_mode?.message}>
              {(id) => (
                <Controller
                  control={form.control}
                  name="billing_mode"
                  render={({ field }) => (
                    <Select value={field.value} onValueChange={field.onChange}>
                      <SelectTrigger id={id} className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {BILLING_MODES.map((m) => (
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
              label="Default currency"
              error={errors.default_currency?.message}
              hint="3-letter ISO code, e.g. USD."
            >
              {(id) => (
                <Input id={id} className="uppercase" maxLength={3} {...form.register("default_currency")} />
              )}
            </FormField>

            <FormField label="Enforcement mode" error={errors.enforcement_mode?.message}>
              {(id) => (
                <Controller
                  control={form.control}
                  name="enforcement_mode"
                  render={({ field }) => (
                    <Select value={field.value} onValueChange={field.onChange}>
                      <SelectTrigger id={id} className="w-full">
                        <SelectValue />
                      </SelectTrigger>
                      <SelectContent>
                        {ENFORCEMENT_MODES.map((m) => (
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

            {!isPostpaid && (
              <>
                <DollarField
                  label="Minimum balance ($)"
                  error={errors.min_balance_micros?.message}
                  hint="Hard floor — spend is blocked below this."
                  register={form.register("min_balance_micros")}
                />
                <DollarField
                  label="Soft minimum balance ($)"
                  error={errors.soft_min_balance_micros?.message}
                  hint="Advisory floor for low-balance signals. Leave blank to disable."
                  register={form.register("soft_min_balance_micros")}
                />
              </>
            )}
            <DollarField
              label="Default task provider-cost limit ($)"
              error={errors.default_task_provider_cost_limit_micros?.message}
              hint="Per-task provider-cost ceiling. Leave blank for none."
              register={form.register("default_task_provider_cost_limit_micros")}
            />
          </div>

          {isPostpaid && (
            <Alert className="mt-4">
              <Info />
              <AlertTitle>Wallet floors not used under postpaid</AlertTitle>
              <AlertDescription>
                Postpaid billing invoices usage at period close rather than gating on a wallet
                floor — the tenant-default minimum and soft-minimum balance fields are hidden
                because they'd have no effect (<code>RiskService.check</code> skips both floor
                checks for postpaid). Per-customer overrides on this tenant's billing profiles are
                inert for the same reason.
              </AlertDescription>
            </Alert>
          )}

          <div className="mt-5 flex flex-col gap-3 border-t border-border pt-4">
            <Controller
              control={form.control}
              name="require_cost_card_coverage"
              render={({ field }) => (
                <CheckboxRow
                  checked={field.value}
                  onChange={field.onChange}
                  label="Require cost-card coverage"
                  description="Reject usage that no rate card can price."
                />
              )}
            />
            <Controller
              control={form.control}
              name="automatic_tax_enabled"
              render={({ field }) => (
                <CheckboxRow
                  checked={field.value}
                  onChange={field.onChange}
                  label="Automatic tax"
                  description="Let Stripe compute tax on invoices."
                />
              )}
            />
            <Controller
              control={form.control}
              name="arrival_signals_enabled"
              render={({ field }) => (
                <CheckboxRow
                  checked={field.value}
                  onChange={field.onChange}
                  label="Arrival signals"
                  description="Emit early-arrival hold signals for async ingestion."
                />
              )}
            />
          </div>
        </Section>
      </form>
    </div>
  );
}

function DollarField({
  label,
  error,
  hint,
  register,
}: {
  label: string;
  error?: string;
  hint?: string;
  register: ReturnType<ReturnType<typeof useForm<GeneralSettingsValues>>["register"]>;
}) {
  return (
    <FormField label={label} error={error} hint={hint}>
      {(id) => <Input id={id} inputMode="decimal" placeholder="0.00" {...register} />}
    </FormField>
  );
}

function toDefaults(config: TenantConfig): GeneralSettingsValues {
  const asMode = <T extends readonly { value: string }[]>(
    list: T,
    value: string,
    fallback: T[number]["value"],
  ) => (list.some((o) => o.value === value) ? (value as T[number]["value"]) : fallback);
  return {
    billing_mode: asMode(BILLING_MODES, config.billing_mode, "meter_only"),
    default_currency: (config.default_currency || "USD").toUpperCase(),
    enforcement_mode: asMode(ENFORCEMENT_MODES, config.enforcement_mode, "off"),
    min_balance_micros: microsToDollars(config.min_balance_micros),
    soft_min_balance_micros: microsToDollars(config.soft_min_balance_micros),
    default_task_provider_cost_limit_micros: microsToDollars(
      config.default_task_provider_cost_limit_micros,
    ),
    require_cost_card_coverage: config.require_cost_card_coverage,
    automatic_tax_enabled: config.automatic_tax_enabled,
    arrival_signals_enabled: config.arrival_signals_enabled,
  };
}
