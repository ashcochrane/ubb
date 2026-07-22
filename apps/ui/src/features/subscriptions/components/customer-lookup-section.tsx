import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FormField } from "@/components/shared/form-field";
import {
  DetailGrid,
  DetailRow,
  ErrorInline,
  LoadingRows,
  Section,
} from "@/components/shared/data-states";
import { StatusBadge } from "@/components/shared/status-badge";
import { formatDate, formatMicros, humanizeLabel } from "@/lib/format";
import { useCustomerSubscription } from "../api/queries";
import {
  customerLookupSchema,
  type CustomerLookupFormValues,
} from "../lib/schema";
import { SubscriptionInvoices } from "./subscription-invoices";

/** Look up one customer's subscription + their subscription invoices. */
export function CustomerLookupSection() {
  const [customerId, setCustomerId] = useState("");
  const subscription = useCustomerSubscription(customerId);
  const {
    register,
    handleSubmit,
    formState: { errors },
  } = useForm<CustomerLookupFormValues>({
    resolver: zodResolver(customerLookupSchema),
    defaultValues: { customerId: "" },
  });

  const onSubmit = (values: CustomerLookupFormValues) =>
    setCustomerId(values.customerId);

  return (
    <Section
      title="Look up a customer subscription"
      description="Enter a customer ID to read their current subscription and invoices."
    >
      <div className="space-y-6">
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="flex items-end gap-2"
        >
          <FormField
            label="Customer ID"
            error={errors.customerId?.message}
            className="flex-1"
          >
            {(id) => (
              <Input id={id} {...register("customerId")} placeholder="cus_… or UBB customer ID" />
            )}
          </FormField>
          <Button type="submit" size="sm" disabled={subscription.isFetching}>
            <Search />
            Look up
          </Button>
        </form>

        {customerId ? (
          subscription.isLoading ? (
            <LoadingRows />
          ) : subscription.isError ? (
            <ErrorInline
              error={subscription.error}
              onRetry={subscription.refetch}
            />
          ) : subscription.data ? (
            <div className="space-y-6">
              <DetailGrid>
                <DetailRow label="Status">
                  <StatusBadge value={subscription.data.status} />
                </DetailRow>
                <DetailRow label="Product">
                  {subscription.data.stripe_product_name}
                </DetailRow>
                <DetailRow label="Amount">
                  {formatMicros(
                    subscription.data.amount_micros,
                    subscription.data.currency,
                  )}{" "}
                  / {humanizeLabel(subscription.data.interval)}
                </DetailRow>
                <DetailRow label="Current period">
                  {formatDate(subscription.data.current_period_start)} –{" "}
                  {formatDate(subscription.data.current_period_end)}
                </DetailRow>
                <DetailRow label="Stripe subscription">
                  <span className="font-mono text-xs">
                    {subscription.data.stripe_subscription_id}
                  </span>
                </DetailRow>
                <DetailRow label="Last synced">
                  {formatDate(subscription.data.last_synced_at)}
                </DetailRow>
              </DetailGrid>

              <div className="space-y-2">
                <h3 className="text-sm font-medium">Invoices</h3>
                <SubscriptionInvoices customerId={customerId} />
              </div>
            </div>
          ) : null
        ) : (
          <p className="text-sm text-muted-foreground">
            No customer looked up yet.
          </p>
        )}
      </div>
    </Section>
  );
}
