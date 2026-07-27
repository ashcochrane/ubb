import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Section,
  LoadingRows,
  ErrorInline,
} from "@/components/shared/data-states";
import { FormField } from "@/components/shared/form-field";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  useBudget,
  usePutBudget,
  useBillingProfile,
  usePutBillingProfile,
} from "../api/queries";
import {
  budgetSchema,
  type BudgetValues,
  billingProfileSchema,
  type BillingProfileValues,
} from "../lib/schema";

const dollars = (micros?: number | null) =>
  micros == null ? undefined : micros / 1_000_000;
const micros = (d?: number) => (d == null ? undefined : Math.round(d * 1_000_000));

export function CustomerBudgetForm({ customerId }: { customerId: string }) {
  const query = useBudget(customerId);
  const save = usePutBudget(customerId);

  const form = useForm<BudgetValues>({
    resolver: zodResolver(budgetSchema),
    values: query.data
      ? {
          cap: (query.data.cap_micros ?? 0) / 1_000_000,
          enforce_mode: (["advisory", "monitor", "enforce"].includes(query.data.enforce_mode)
            ? query.data.enforce_mode
            : "advisory") as BudgetValues["enforce_mode"],
          hard_stop_pct: query.data.hard_stop_pct ?? 100,
          fail_closed: query.data.fail_closed ?? false,
        }
      : undefined,
  });

  const onSubmit = form.handleSubmit((v) =>
    save.mutate({
      cap_micros: Math.round(v.cap * 1_000_000),
      enforce_mode: v.enforce_mode,
      hard_stop_pct: v.hard_stop_pct,
      fail_closed: v.fail_closed,
      alert_levels: query.data?.alert_levels ?? [],
    }),
  );

  return (
    <Section
      title="Spend budget"
      description="Cap this customer's spend. Enforcement can block usage or just alert."
    >
      {query.isLoading ? (
        <LoadingRows rows={2} />
      ) : query.isError ? (
        <ErrorInline error={query.error} onRetry={() => query.refetch()} />
      ) : (
        <form onSubmit={onSubmit} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField label="Cap (USD)" error={form.formState.errors.cap?.message}>
              {(id) => <Input id={id} type="number" min={0} step={0.01} {...form.register("cap", { valueAsNumber: true })} />}
            </FormField>
            <FormField label="Enforcement" error={form.formState.errors.enforce_mode?.message}>
              {() => (
                <Controller
                  control={form.control}
                  name="enforce_mode"
                  render={({ field }) => (
                    <Select value={field.value} onValueChange={field.onChange}>
                      <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="advisory">Advisory (track only)</SelectItem>
                        <SelectItem value="monitor">Monitor (alert)</SelectItem>
                        <SelectItem value="enforce">Enforce (block)</SelectItem>
                      </SelectContent>
                    </Select>
                  )}
                />
              )}
            </FormField>
            <FormField label="Hard-stop at (% of cap)" error={form.formState.errors.hard_stop_pct?.message}>
              {(id) => <Input id={id} type="number" min={0} max={1000} {...form.register("hard_stop_pct", { valueAsNumber: true })} />}
            </FormField>
          </div>
          <Controller
            control={form.control}
            name="fail_closed"
            render={({ field }) => (
              <label className="flex items-center gap-2 text-sm">
                <input type="checkbox" className="size-4 accent-foreground" checked={field.value} onChange={(e) => field.onChange(e.target.checked)} />
                Fail closed — block usage if the budget can't be evaluated
              </label>
            )}
          />
          <Button type="submit" disabled={save.isPending}>
            {save.isPending ? "Saving…" : "Save budget"}
          </Button>
        </form>
      )}
    </Section>
  );
}

export function CustomerBillingProfileForm({ customerId }: { customerId: string }) {
  const query = useBillingProfile(customerId);
  const save = usePutBillingProfile(customerId);

  const form = useForm<BillingProfileValues>({
    resolver: zodResolver(billingProfileSchema),
    values: query.data
      ? {
          min_balance: dollars(query.data.min_balance_micros),
          soft_min_balance: dollars(query.data.soft_min_balance_micros),
          topup_grant_expiry_days: query.data.topup_grant_expiry_days ?? undefined,
        }
      : undefined,
  });

  const onSubmit = form.handleSubmit((v) =>
    save.mutate({
      min_balance_micros: micros(v.min_balance) ?? null,
      soft_min_balance_micros: micros(v.soft_min_balance) ?? null,
      topup_grant_expiry_days: v.topup_grant_expiry_days ?? null,
    }),
  );

  const num = (name: keyof BillingProfileValues) =>
    form.register(name, {
      setValueAs: (v) => (v === "" || v == null || Number.isNaN(Number(v)) ? undefined : Number(v)),
    });

  return (
    <Section
      title="Billing profile"
      description="Minimum-balance floors that gate usage when the wallet runs low."
    >
      {query.isLoading ? (
        <LoadingRows rows={2} />
      ) : query.isError ? (
        <ErrorInline error={query.error} onRetry={() => query.refetch()} />
      ) : (
        <form onSubmit={onSubmit} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-3">
            <FormField label="Hard min balance (USD)" hint="Blocks below this" error={form.formState.errors.min_balance?.message}>
              {(id) => <Input id={id} type="number" step={0.01} {...num("min_balance")} />}
            </FormField>
            <FormField label="Soft min balance (USD)" hint="Warns below this" error={form.formState.errors.soft_min_balance?.message}>
              {(id) => <Input id={id} type="number" step={0.01} {...num("soft_min_balance")} />}
            </FormField>
            <FormField label="Top-up grant expiry (days)" hint="Optional" error={form.formState.errors.topup_grant_expiry_days?.message}>
              {(id) => <Input id={id} type="number" min={1} {...num("topup_grant_expiry_days")} />}
            </FormField>
          </div>
          <Button type="submit" disabled={save.isPending}>
            {save.isPending ? "Saving…" : "Save profile"}
          </Button>
        </form>
      )}
    </Section>
  );
}
