import { useNavigate } from "@tanstack/react-router";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { ArrowLeft } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FormField } from "@/components/shared/form-field";
import {
  Section,
  DetailGrid,
  DetailRow,
  QueryState,
  ProductUnavailable,
} from "@/components/shared/data-states";
import { formatMicros, formatPercentMicros } from "@/lib/format";
import { useAuth } from "@/features/auth/hooks/use-auth";
import { useMarkup, useUpdateMarkup } from "../api/queries";
import { markupSchema, type MarkupValues } from "../lib/schema";
import type { TenantMarkup } from "../api/types";

export function MarkupPage() {
  const { hasProduct } = useAuth();
  const navigate = useNavigate();
  const query = useMarkup();

  if (!hasProduct("metering")) {
    return (
      <div className="space-y-6">
        <PageHeader title="Markup" />
        <ProductUnavailable product="Metering" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Default markup"
        description="Markup is applied on top of provider cost to compute the customer's billed price."
        actions={
          <Button variant="ghost" size="sm" onClick={() => navigate({ to: "/pricing" })}>
            <ArrowLeft />
            Back
          </Button>
        }
      />

      <QueryState query={query}>
        {(markup) => <MarkupForm markup={markup} />}
      </QueryState>
    </div>
  );
}

function MarkupForm({ markup }: { markup: TenantMarkup }) {
  const update = useUpdateMarkup();

  const form = useForm<MarkupValues>({
    resolver: zodResolver(markupSchema),
    values: {
      percentage: markup.markup_percentage_micros / 1_000_000,
      fixed_uplift: markup.fixed_uplift_micros / 1_000_000,
    },
  });
  const { errors } = form.formState;

  const onSubmit = form.handleSubmit((values) => {
    update.mutate({
      markup_percentage_micros: Math.round(values.percentage * 1_000_000),
      fixed_uplift_micros: Math.round(values.fixed_uplift * 1_000_000),
    });
  });

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Section title="Edit markup">
        <form onSubmit={onSubmit} className="flex flex-col gap-4">
          <FormField
            label="Markup percentage"
            error={errors.percentage?.message}
            hint="e.g. 20 means the customer is billed 20% above provider cost."
          >
            {(id) => (
              <Input
                id={id}
                type="number"
                min={0}
                step="any"
                {...form.register("percentage", { valueAsNumber: true })}
              />
            )}
          </FormField>

          <FormField
            label="Fixed uplift (USD)"
            error={errors.fixed_uplift?.message}
            hint="A flat amount added per priced event, on top of the percentage."
          >
            {(id) => (
              <Input
                id={id}
                type="number"
                min={0}
                step="any"
                {...form.register("fixed_uplift", { valueAsNumber: true })}
              />
            )}
          </FormField>

          <div className="flex justify-end">
            <Button type="submit" disabled={update.isPending}>
              {update.isPending ? "Saving…" : "Save markup"}
            </Button>
          </div>
        </form>
      </Section>

      <Section
        title="Current markup"
        description="What's applied today across customers without a specific override."
      >
        <DetailGrid className="sm:grid-cols-1">
          <DetailRow label="Markup percentage">
            {formatPercentMicros(markup.markup_percentage_micros)}
          </DetailRow>
          <DetailRow label="Fixed uplift">
            {formatMicros(markup.fixed_uplift_micros)}
          </DetailRow>
        </DetailGrid>
      </Section>
    </div>
  );
}
