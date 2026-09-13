// The Customer Spend Pool on the customer's Billing tab (#468; slice 6 §4,
// §18): where the customer's known period charges stand against the pool
// that applies to them, said as words, and the declaration a finance
// operator edits. The PUT is a FULL upsert with schema defaults, so the
// form is prefilled from GET and every field is always sent on save.
//
// WHAT THE CARD SAYS, in order: the LEVEL the pool applies at (this
// customer's own, the workspace default for seats, or none); the PAIR — the
// known charges against the pool, the share used, the headroom — with
// unknown revenue reported as EXCLUDED and never summed as zero (#150
// §4.2); the pool's MODE as the catalogue's word beside the posture in a
// sentence; the refusal, where the known charges are at or over the stop
// line; and the two sentences that keep the pool apart from the wallet —
// the different question it answers (#151 §11.3) and its blindness to a
// price agreed at start until delivery (#150 §7.5). No meter, no amber, no
// warning affordance: enforcement is binary (#150 §9.4; #152 §4) and the
// pool's alert levels are what it announces, not a state the card draws.
//
// The words and the readers are `@/lib/spend-pool`'s, shared with the
// Utilisation and headroom report; the pair's kind sits on the node
// (`data-reading`, `data-pool-*`) so a test asserts WHICH reading it holds
// rather than matching prose the wrong one could satisfy.

import * as React from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { toast } from "sonner";

import { problemMessage } from "@/api/problem";
import { DetailList } from "@/components/shared/detail-list";
import { ErrorCard } from "@/components/shared/error-card";
import { FormField } from "@/components/shared/form-field";
import { Reading } from "@/components/shared/reading";
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
import { formatMicros } from "@/lib/format";
import { ABSENT_LABEL } from "@/lib/localisation";
import {
  describePoolHeadroom,
  describePoolUtilisation,
  excludedFromKnown,
  POOL_AND_WALLET_DIFFER,
  POOL_BLIND_TO_FIXED_PRICE,
  POOL_LEVEL,
  POOL_PAIR_TITLE,
  POOL_POSTURE,
  poolLevel,
  readPoolCharges,
  SPEND_POOL_ENFORCE_MODE_WORDS,
  spendPoolEnforceModeLabel,
  STARTS_REFUSED,
  type CustomerSpendPoolStatus,
} from "@/lib/spend-pool";
import { SPEND_POOL_ENFORCE_MODE_VALUES } from "@/lib/vocabulary";

import {
  useCustomerSpendPool,
  useCustomerSpendPoolStatus,
  useSaveCustomerSpendPool,
} from "../api/queries";
import type { CustomerSpendPoolOut } from "../api/types";
import { formatAlertLevels, microsToUnits, parseAlertLevels, toMicros } from "../lib/helpers";
import { customerSpendPoolSchema, type CustomerSpendPoolForm } from "../lib/schemas";

/** The heading of the standing — what the pair is read under. */
export const POOL_STANDING_TITLE = "Where this customer's pool stands";

/** A figure the wire left null, rendered as the absence it is. */
function Absent() {
  return <span className="text-text-muted">{ABSENT_LABEL}</span>;
}

/**
 * The level, the pair and the posture, as words. The pair renders whether
 * or not a pool applies — the charges are real either way — and the
 * assessment beside it only where one does.
 */
function PoolStanding({
  declared,
  status,
  currency,
}: {
  declared: CustomerSpendPoolOut;
  status: CustomerSpendPoolStatus;
  currency: string;
}) {
  const level = poolLevel(declared, status);
  const applies = status.cap_micros > 0;
  const used = describePoolUtilisation(status);
  const headroom = describePoolHeadroom(status, currency);
  const excluded = excludedFromKnown(status);
  return (
    <section aria-label={POOL_STANDING_TITLE} className="space-y-2" data-pool-level={level}>
      <p className="text-[12px] text-text-secondary">{POOL_LEVEL[level]}</p>
      <DetailList
        items={[
          { label: "Period", value: status.period },
          {
            label: "Known period charges",
            value: applies ? (
              <span>
                <Reading reading={readPoolCharges(status)} currency={currency} /> of{" "}
                {formatMicros(status.cap_micros, currency)}
              </span>
            ) : (
              <Reading reading={readPoolCharges(status)} currency={currency} />
            ),
          },
          ...(applies
            ? [
                {
                  label: "Used",
                  value: <span data-pool-figure="used">{used ?? <Absent />}</span>,
                },
                {
                  label: "Headroom",
                  value: <span data-pool-figure="headroom">{headroom ?? <Absent />}</span>,
                },
                {
                  label: "Mode",
                  value: (
                    <span data-pool-mode={status.enforce_mode}>
                      {spendPoolEnforceModeLabel(status.enforce_mode)}
                    </span>
                  ),
                },
              ]
            : []),
        ]}
      />
      {excluded && (
        <p className="text-[12px] text-text-secondary" data-pool-excluded>
          {excluded}
        </p>
      )}
      {applies && (
        <p className="text-[12px] text-text-secondary" data-pool-posture={status.enforce_mode}>
          {POOL_POSTURE[status.enforce_mode]}
        </p>
      )}
      {status.blocking_occurred && (
        <p className="text-[12px] text-text-primary" data-pool-blocking>
          {STARTS_REFUSED}
        </p>
      )}
    </section>
  );
}

export function CustomerSpendPoolSection({ customerId }: { customerId: string }) {
  const currency = useTenantCurrency();
  const isAdmin = useHasRole("admin");
  const declared = useCustomerSpendPool(customerId);
  const status = useCustomerSpendPoolStatus(customerId);
  const mutation = useSaveCustomerSpendPool(customerId);

  const form = useForm<CustomerSpendPoolForm>({
    resolver: zodResolver(customerSpendPoolSchema),
    defaultValues: {
      cap: "",
      enforce_mode: "alert_only",
      hard_stop_pct: "100",
      alert_levels: "",
      fail_closed: false,
    },
  });

  const config = declared.data;
  React.useEffect(() => {
    if (config) {
      form.reset({
        cap: microsToUnits(config.cap_micros),
        // The registry's closed pair, narrowed by the generated type: no
        // unknown branch to fall back from.
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
      toast.success("Customer spend pool saved");
    } catch {
      // surfaced below
    }
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>{POOL_PAIR_TITLE}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {status.isLoading || declared.isLoading ? (
          <Skeleton className="h-24 w-full" />
        ) : status.isError ? (
          <ErrorCard error={status.error} onRetry={() => void status.refetch()} />
        ) : declared.isError ? (
          <ErrorCard error={declared.error} onRetry={() => void declared.refetch()} />
        ) : status.data && declared.data ? (
          <PoolStanding declared={declared.data} status={status.data} currency={currency} />
        ) : null}

        <p className="text-[12px] text-text-secondary">{POOL_AND_WALLET_DIFFER}</p>
        <p className="text-[12px] text-text-secondary">{POOL_BLIND_TO_FIXED_PRICE}</p>

        {declared.isLoading ? (
          <Skeleton className="h-40 w-full" />
        ) : declared.isError ? null : (
          <form onSubmit={(event) => void submit(event)} className="space-y-2.5">
            <p className="text-[11px] text-text-muted">
              Saving writes the whole declaration exactly as shown — fields left at
              defaults are saved as defaults, not preserved. An amount of nothing
              declares no pool.
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
                hint="Alert only announces each level reached; Blocking also refuses new starts and stops active work at the stop line."
              >
                {() => (
                  <Select
                    value={form.watch("enforce_mode")}
                    items={SPEND_POOL_ENFORCE_MODE_WORDS}
                    onValueChange={(value) =>
                      form.setValue("enforce_mode", value ?? "alert_only")
                    }
                  >
                    <SelectTrigger className="w-full" aria-label="Enforce mode">
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
              </FormField>
            </div>
            <div className="grid grid-cols-2 gap-2.5">
              <FormField
                label="Stop line (% of cap)"
                error={form.formState.errors.hard_stop_pct?.message}
                hint="1–1000. 100 = the stop line is the cap itself."
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
                id="pool-fail-closed"
                checked={form.watch("fail_closed")}
                onCheckedChange={(checked) => form.setValue("fail_closed", checked)}
              />
              <Label htmlFor="pool-fail-closed">
                Fail closed — refuse starts when the pool's standing can't be read
              </Label>
            </div>
            {mutation.error != null && (
              <p className="text-[12px] text-danger-dark" role="alert">
                {problemMessage(mutation.error)}
              </p>
            )}
            <div className="flex items-center gap-2">
              <Button type="submit" size="sm" disabled={mutation.isPending || !isAdmin}>
                {mutation.isPending ? "Working…" : "Save pool"}
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
