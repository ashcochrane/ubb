// Send-test-event console: a form over POST /metering/usage (write floor)
// with a response column that keeps the last few priced responses so users
// can compare runs. The idempotency key is generated once and only replaced
// after a success, so a retry after failure replays safely.

import { useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useFieldArray, useForm } from "react-hook-form";
import { Plus, RefreshCw, X } from "lucide-react";

import { problemMessage } from "@/api/problem";
import { FormField } from "@/components/shared/form-field";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
} from "@/components/ui/select";
import { useHasRole } from "@/hooks/use-current-role";
import { useTenantCurrency } from "@/hooks/use-tenant-config";

import { useMarginCustomers, useSendTestEvent } from "../api/queries";
import {
  EMPTY_METRIC_ROW,
  buildTestEventRequest,
  shortenUuid,
  testEventFormSchema,
  type TestEventFormValues,
} from "../lib/test-event";
import { TestEventResponseCard, type TestEventEntry } from "./test-event-response";

const MAX_HISTORY = 5;

export function TestEventConsole() {
  const currency = useTenantCurrency();
  const customers = useMarginCustomers();
  const send = useSendTestEvent();
  const canWrite = useHasRole("write");
  const [history, setHistory] = useState<TestEventEntry[]>([]);
  const [picked, setPicked] = useState<string | null>(null);

  const form = useForm<TestEventFormValues>({
    resolver: zodResolver(testEventFormSchema),
    defaultValues: {
      customer_id: "",
      event_type: "",
      provider: "",
      product_id: "",
      provider_cost: "",
      billed_cost: "",
      effective_at: "",
      idempotency_key: crypto.randomUUID(),
      metrics: [{ ...EMPTY_METRIC_ROW }],
    },
  });
  const metricRows = useFieldArray({ control: form.control, name: "metrics" });
  const errors = form.formState.errors;

  const submit = form.handleSubmit((values) => {
    const body = buildTestEventRequest(values, `console-${crypto.randomUUID()}`);
    send.mutate(body, {
      onSuccess: (response) => {
        setHistory((previous) =>
          [
            {
              id: crypto.randomUUID(),
              at: new Date().toISOString(),
              eventType: values.event_type,
              response,
            },
            ...previous,
          ].slice(0, MAX_HISTORY),
        );
        // Replay-safe: a NEW key only after success; a failed attempt
        // keeps the old key so retries dedupe server-side.
        form.setValue("idempotency_key", crypto.randomUUID());
      },
    });
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle>Send a test event</CardTitle>
        <CardDescription>
          Records a real usage event through POST /metering/usage and shows the
          priced response — costs, balance movement, and any stop verdict.
          {!canWrite && " Sending requires the Write role."}
        </CardDescription>
      </CardHeader>
      <CardContent>
        <div className="grid gap-6 lg:grid-cols-2">
          <form onSubmit={(event) => void submit(event)} className="space-y-4">
            <div className="space-y-1.5">
              <Label htmlFor="test-event-customer">Customer</Label>
              <div className="flex flex-col gap-1.5 sm:flex-row">
                <Select
                  value={picked}
                  onValueChange={(value) => {
                    if (typeof value !== "string") return;
                    setPicked(value);
                    form.setValue("customer_id", value, { shouldValidate: true });
                  }}
                >
                  <SelectTrigger
                    className="w-full sm:w-[170px]"
                    aria-label="Pick a customer"
                    disabled={customers.isLoading || (customers.data ?? []).length === 0}
                  >
                    <span className="truncate font-mono text-[12px]">
                      {picked
                        ? shortenUuid(picked)
                        : customers.isLoading
                          ? "Loading…"
                          : "Pick a customer"}
                    </span>
                  </SelectTrigger>
                  <SelectContent>
                    {(customers.data ?? []).map((row) => (
                      <SelectItem key={row.customer_id} value={row.customer_id}>
                        <span className="font-mono text-[12px]">
                          {shortenUuid(row.customer_id)}
                        </span>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Input
                  id="test-event-customer"
                  placeholder="…or paste a customer UUID"
                  className="font-mono text-[12px]"
                  {...form.register("customer_id", {
                    onChange: () => setPicked(null),
                  })}
                />
              </div>
              {errors.customer_id ? (
                <p className="text-xs text-destructive">{errors.customer_id.message}</p>
              ) : (
                <p className="text-xs text-muted-foreground">
                  The UBB customer UUID (not your external id).
                  {customers.isError && " Couldn't load recent customers — paste a UUID."}
                </p>
              )}
            </div>

            <div className="grid grid-cols-2 gap-3">
              <FormField label="Event type" error={errors.event_type?.message}>
                {(id) => (
                  <Input id={id} placeholder="chat_completion" {...form.register("event_type")} />
                )}
              </FormField>
              <FormField label="Provider" error={errors.provider?.message}>
                {(id) => (
                  <Input id={id} placeholder="anthropic" {...form.register("provider")} />
                )}
              </FormField>
              <FormField label="Product" error={errors.product_id?.message}>
                {(id) => (
                  <Input id={id} placeholder="assistant-pro" {...form.register("product_id")} />
                )}
              </FormField>
            </div>

            <div className="space-y-1.5">
              <Label>Usage metrics</Label>
              {metricRows.fields.map((field, index) => (
                <div key={field.id} className="flex items-start gap-1.5">
                  <div className="flex-1">
                    <Input
                      aria-label={`Metric ${index + 1} name`}
                      placeholder="tokens_in"
                      className="font-mono text-[12px]"
                      {...form.register(`metrics.${index}.key`)}
                    />
                    {errors.metrics?.[index]?.key && (
                      <p className="mt-1 text-xs text-destructive">
                        {errors.metrics[index]?.key?.message}
                      </p>
                    )}
                  </div>
                  <div className="flex-1">
                    <Input
                      aria-label={`Metric ${index + 1} quantity`}
                      inputMode="numeric"
                      placeholder="1200"
                      className="font-mono text-[12px]"
                      {...form.register(`metrics.${index}.value`)}
                    />
                    {errors.metrics?.[index]?.value && (
                      <p className="mt-1 text-xs text-destructive">
                        {errors.metrics[index]?.value?.message}
                      </p>
                    )}
                  </div>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    aria-label={`Remove metric ${index + 1}`}
                    onClick={() => metricRows.remove(index)}
                    disabled={metricRows.fields.length === 1}
                  >
                    <X />
                  </Button>
                </div>
              ))}
              <Button
                type="button"
                variant="outline"
                size="sm"
                onClick={() => metricRows.append({ ...EMPTY_METRIC_ROW })}
              >
                <Plus data-icon="inline-start" />
                Add metric
              </Button>
              <p className="text-xs text-muted-foreground">
                Metric name → whole-number quantity, priced by your rate cards.
                Metrics without a cost card come back flagged as uncosted.
              </p>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <FormField
                label={`Provider cost (${currency.toUpperCase()})`}
                error={errors.provider_cost?.message}
                hint="Optional — your cost of goods."
              >
                {(id) => (
                  <Input id={id} inputMode="decimal" placeholder="0.42" {...form.register("provider_cost")} />
                )}
              </FormField>
              <FormField
                label={`Billed cost (${currency.toUpperCase()})`}
                error={errors.billed_cost?.message}
                hint="Optional — overrides pricing. Converted to micros."
              >
                {(id) => (
                  <Input id={id} inputMode="decimal" placeholder="0.60" {...form.register("billed_cost")} />
                )}
              </FormField>
            </div>

            <FormField
              label="Effective at"
              error={errors.effective_at?.message}
              hint="Optional backfill timestamp. Sent as timezone-aware UTC — the API rejects naive timestamps and future dates."
            >
              {(id) => (
                <Input id={id} type="datetime-local" {...form.register("effective_at")} />
              )}
            </FormField>

            <FormField
              label="Idempotency key"
              error={errors.idempotency_key?.message}
              hint="Replay-safe: resending with the same key returns the original event instead of recording twice. A fresh key is generated after each success."
            >
              {(id) => (
                <div className="flex gap-1.5">
                  <Input
                    id={id}
                    readOnly
                    className="font-mono text-[12px]"
                    {...form.register("idempotency_key")}
                  />
                  <Button
                    type="button"
                    variant="outline"
                    size="icon"
                    aria-label="Regenerate idempotency key"
                    onClick={() =>
                      form.setValue("idempotency_key", crypto.randomUUID())
                    }
                  >
                    <RefreshCw />
                  </Button>
                </div>
              )}
            </FormField>

            {send.isError && (
              <p className="text-xs text-destructive">{problemMessage(send.error)}</p>
            )}
            <Button type="submit" disabled={send.isPending || !canWrite}>
              {send.isPending ? "Working…" : "Send test event"}
            </Button>
          </form>

          <div className="space-y-3">
            <div>
              <p className="text-[13px] font-medium text-text-primary">Responses</p>
              <p className="text-[12px] text-text-secondary">
                Latest first — the last {MAX_HISTORY} are kept for this session
                so you can compare runs.
              </p>
            </div>
            {history.length === 0 ? (
              <div className="rounded-lg border border-dashed border-border p-6 text-center text-[12px] text-text-muted">
                Send an event to see the priced response here.
              </div>
            ) : (
              history.map((entry) => (
                <TestEventResponseCard key={entry.id} entry={entry} currency={currency} />
              ))
            )}
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
