import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Section, DetailGrid, DetailRow } from "@/components/shared/data-states";
import { FormField } from "@/components/shared/form-field";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { StatusBadge } from "@/components/shared/status-badge";
import { formatMicros, truncateId } from "@/lib/format";
import { usePreCheck } from "../api/queries";
import { preCheckSchema, type PreCheckFormValues } from "../lib/schema";

export function PreCheckSection() {
  const preCheck = usePreCheck();
  const {
    register,
    handleSubmit,
    control,
    formState: { errors, isValid },
  } = useForm<PreCheckFormValues>({
    resolver: zodResolver(preCheckSchema),
    mode: "onChange",
    defaultValues: {
      customerId: "",
      startTask: false,
      externalTaskId: "",
      providerCostLimit: undefined,
    },
  });

  const run = handleSubmit((v) =>
    preCheck.mutate({
      customer_id: v.customerId,
      start_task: v.startTask,
      external_task_id: v.externalTaskId,
      provider_cost_limit_micros:
        v.providerCostLimit === undefined
          ? null
          : Math.round(v.providerCostLimit * 1_000_000),
    }),
  );

  const startTask = useWatch({ control, name: "startTask" });
  const result = preCheck.data;

  return (
    <Section
      title="Spend pre-check (advanced)"
      description="Ask the gate whether a customer may spend right now. With 'start task' enabled, this also opens a task and holds against its cost limit."
    >
      <div className="space-y-4">
        <form className="space-y-4" onSubmit={(e) => e.preventDefault()}>
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField label="Customer ID" error={errors.customerId?.message}>
              {(id) => <Input id={id} {...register("customerId")} />}
            </FormField>
            <FormField
              label="Provider cost limit (USD, optional)"
              error={errors.providerCostLimit?.message}
              hint="Per-task upstream cost ceiling to hold against."
            >
              {(id) => (
                <Input
                  id={id}
                  type="number"
                  min={0}
                  step={0.01}
                  {...register("providerCostLimit", {
                    setValueAs: (v) =>
                      v === "" || v === null ? undefined : Number(v),
                  })}
                />
              )}
            </FormField>
            <FormField label="External task ID (optional)">
              {(id) => <Input id={id} {...register("externalTaskId")} />}
            </FormField>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="size-4 accent-foreground"
              {...register("startTask")}
            />
            Start a task and place a hold (this gates real spend)
          </label>
          <ConfirmDialog
            trigger={
              <Button disabled={!isValid || preCheck.isPending}>
                {preCheck.isPending ? "Checking…" : "Run pre-check"}
              </Button>
            }
            title="Run this pre-check?"
            description={
              startTask
                ? "This starts a task and places a hold against the customer's balance — it gates real spend."
                : "This performs a read-only spend check for the customer."
            }
            confirmLabel="Run pre-check"
            onConfirm={run}
          />
        </form>

        {result && (
          <div className="rounded-lg border border-border p-4">
            <DetailGrid>
              <DetailRow label="Allowed">
                <StatusBadge
                  value={result.allowed ? "allowed" : "blocked"}
                  tone={result.allowed ? "solid" : "danger"}
                />
              </DetailRow>
              <DetailRow label="Reason">
                {result.reason ? result.reason : "—"}
              </DetailRow>
              <DetailRow label="Balance">
                {result.balance_micros != null
                  ? formatMicros(result.balance_micros)
                  : "—"}
              </DetailRow>
              <DetailRow label="Task ID">
                {result.task_id ? (
                  <span className="font-mono text-xs">
                    {truncateId(result.task_id)}
                  </span>
                ) : (
                  "—"
                )}
              </DetailRow>
              <DetailRow label="Provider cost limit">
                {result.provider_cost_limit_micros != null
                  ? formatMicros(result.provider_cost_limit_micros)
                  : "—"}
              </DetailRow>
              <DetailRow label="Floor snapshot">
                {result.floor_snapshot_micros != null
                  ? formatMicros(result.floor_snapshot_micros)
                  : "—"}
              </DetailRow>
            </DetailGrid>
          </div>
        )}
      </div>
    </Section>
  );
}
