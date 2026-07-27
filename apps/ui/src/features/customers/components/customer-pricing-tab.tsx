import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Section,
  LoadingRows,
  ErrorInline,
} from "@/components/shared/data-states";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { FormField } from "@/components/shared/form-field";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  useCustomerMarkup,
  usePutCustomerMarkup,
  useDeleteCustomerMarkup,
  useAssignRateCard,
} from "../api/queries";
import { markupSchema, type MarkupValues } from "../lib/schema";

/** Per-customer pricing overrides: a markup override and rate-card assignment. */
export function CustomerPricingTab({ customerId }: { customerId: string }) {
  return (
    <div className="space-y-6">
      <MarkupOverride customerId={customerId} />
      <AssignRateCard customerId={customerId} />
    </div>
  );
}

function MarkupOverride({ customerId }: { customerId: string }) {
  const query = useCustomerMarkup(customerId);
  const save = usePutCustomerMarkup(customerId);
  const remove = useDeleteCustomerMarkup(customerId);

  const form = useForm<MarkupValues>({
    resolver: zodResolver(markupSchema),
    values: query.data
      ? {
          markup_percentage: (query.data.markup_percentage_micros ?? 0) / 1_000_000,
          fixed_uplift: (query.data.fixed_uplift_micros ?? 0) / 1_000_000,
        }
      : undefined,
  });

  const onSubmit = form.handleSubmit((v) =>
    save.mutate({
      markup_percentage_micros: Math.round(v.markup_percentage * 1_000_000),
      fixed_uplift_micros: Math.round(v.fixed_uplift * 1_000_000),
    }),
  );

  return (
    <Section
      title="Markup override"
      description="Overrides the tenant-default markup for this customer. Applied on top of provider cost."
      actions={
        <ConfirmDialog
          destructive
          title="Remove markup override?"
          description="This customer will fall back to the tenant-default markup."
          confirmLabel="Remove override"
          onConfirm={() => remove.mutateAsync()}
          trigger={<Button variant="outline" size="sm" disabled={remove.isPending}>Reset to default</Button>}
        />
      }
    >
      {query.isLoading ? (
        <LoadingRows rows={2} />
      ) : query.isError ? (
        <ErrorInline error={query.error} onRetry={() => query.refetch()} />
      ) : (
        <form onSubmit={onSubmit} className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <FormField label="Markup (%)" hint="Percentage added to provider cost" error={form.formState.errors.markup_percentage?.message}>
              {(id) => <Input id={id} type="number" min={0} step={0.1} {...form.register("markup_percentage", { valueAsNumber: true })} />}
            </FormField>
            <FormField label="Fixed uplift (USD)" hint="Flat amount added per unit" error={form.formState.errors.fixed_uplift?.message}>
              {(id) => <Input id={id} type="number" min={0} step={0.01} {...form.register("fixed_uplift", { valueAsNumber: true })} />}
            </FormField>
          </div>
          <Button type="submit" disabled={save.isPending}>
            {save.isPending ? "Saving…" : "Save markup"}
          </Button>
        </form>
      )}
    </Section>
  );
}

function AssignRateCard({ customerId }: { customerId: string }) {
  const [rateCardId, setRateCardId] = useState("");
  const assign = useAssignRateCard(customerId);
  return (
    <Section
      title="Rate card assignment"
      description="Assign a specific rate card (book) to price this customer's usage."
    >
      <div className="flex items-end gap-2">
        <FormField label="Rate card ID" className="flex-1">
          {(id) => (
            <Input
              id={id}
              placeholder="book id…"
              value={rateCardId}
              onChange={(e) => setRateCardId(e.target.value)}
            />
          )}
        </FormField>
        <Button
          onClick={() => assign.mutate(rateCardId.trim())}
          disabled={!rateCardId.trim() || assign.isPending}
        >
          {assign.isPending ? "Assigning…" : "Assign"}
        </Button>
      </div>
    </Section>
  );
}
