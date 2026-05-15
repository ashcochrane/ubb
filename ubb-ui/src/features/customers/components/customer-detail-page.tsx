import { useEffect } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FormField } from "@/components/shared/form-field";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import {
  useCustomer,
  useDeleteCustomer,
  useUpdateCustomer,
} from "../api/queries";
import { CustomerBillingPanel } from "@/features/billing-ops/components/customer-billing-panel";
import { CUSTOMER_STATUSES, type CustomerStatus } from "../api/types";
import {
  customerEditSchema,
  type CustomerEditFormValues,
} from "../lib/schema";

export function CustomerDetailPage({ customerId }: { customerId: string }) {
  const { data, isLoading } = useCustomer(customerId);
  const update = useUpdateCustomer(customerId);
  const remove = useDeleteCustomer();
  const navigate = useNavigate();

  const { register, handleSubmit, reset, formState: { errors } } =
    useForm<CustomerEditFormValues>({
      resolver: zodResolver(customerEditSchema),
      defaultValues: { stripeCustomerId: "", status: "active" },
    });

  // Sync form with server data when the customer record loads or changes.
  // Depend on primitive values rather than the object reference to avoid
  // re-firing on every render when the query hook returns a new object literal.
  const stripeId = data?.stripeCustomerId ?? "";
  const statusVal = (data?.status as CustomerStatus) ?? "active";
  useEffect(() => {
    if (!data) return;
    reset({ stripeCustomerId: stripeId, status: statusVal });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stripeId, statusVal]);

  if (isLoading || !data) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-48 w-full max-w-xl" />
      </div>
    );
  }

  async function onSubmit(values: CustomerEditFormValues) {
    await update.mutateAsync({
      stripeCustomerId: values.stripeCustomerId,
      status: values.status,
      minBalanceMicros: data?.minBalanceMicros ?? null,
      metadata: data?.metadata ?? {},
    });
  }

  async function onDelete() {
    if (!confirm(`Delete customer ${data?.externalId}?`)) return;
    await remove.mutateAsync(customerId);
    navigate({ to: "/customers" });
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={data.externalId}
        description={`Created ${new Date(data.createdAt).toLocaleString()}`}
        actions={
          <Button variant="destructive" onClick={onDelete} disabled={remove.isPending}>
            Delete
          </Button>
        }
      />
      <Card className="max-w-xl">
        <CardHeader>
          <CardTitle className="text-base">Details</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            <FormField label="External ID" hint="External ID is immutable.">
              {(id) => <Input id={id} value={data.externalId} disabled />}
            </FormField>
            <FormField
              label="Stripe customer ID"
              error={errors.stripeCustomerId?.message}
            >
              {(id) => <Input id={id} {...register("stripeCustomerId")} />}
            </FormField>
            <FormField label="Status" error={errors.status?.message}>
              {(id) => (
                <select
                  id={id}
                  className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
                  {...register("status")}
                >
                  {CUSTOMER_STATUSES.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              )}
            </FormField>
            <Button type="submit" disabled={update.isPending}>
              {update.isPending ? "Saving…" : "Save changes"}
            </Button>
          </form>
        </CardContent>
      </Card>
      <CustomerBillingPanel customerId={customerId} />
    </div>
  );
}
