// Stripe subscription mirror for one customer. Reads key on the customer
// UUID; lifecycle verbs go through the platform external_id routes (untyped
// responses — we only care that they succeed, then refetch the mirror).

import * as React from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { CreditCard } from "lucide-react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";

import { problemMessage } from "@/api/problem";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { DetailList } from "@/components/shared/detail-list";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorCard } from "@/components/shared/error-card";
import { FormField } from "@/components/shared/form-field";
import { LoadMore } from "@/components/shared/load-more";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useHasRole } from "@/hooks/use-current-role";
import { formatDate, formatMicros, formatShortDate } from "@/lib/format";
import { planIntervalLabel, subscriptionStatusLabel } from "@/lib/labels";

import {
  useCancelSubscription,
  usePauseSubscription,
  useResumeSubscription,
  useSetSeats,
  useSubscribe,
  useSubscription,
  useSubscriptionInvoices,
} from "../api/queries";
import type { StripeSubscriptionOut } from "../api/types";
import {
  seatsSchema,
  subscribeSchema,
  type SeatsForm,
  type SubscribeForm,
} from "../lib/schemas";

export function SubscriptionTab({
  customerId,
  externalId,
}: {
  customerId: string;
  externalId: string;
}) {
  const query = useSubscription(customerId);

  if (query.isLoading) return <Skeleton className="h-48 w-full" />;
  if (query.isError) {
    return <ErrorCard error={query.error} onRetry={() => void query.refetch()} />;
  }

  const subscription = query.data ?? null;
  if (!subscription) {
    return <SubscribeCard externalId={externalId} />;
  }
  return (
    <div className="space-y-4">
      <ActiveSubscriptionCard subscription={subscription} externalId={externalId} />
      <InvoicesCard customerId={customerId} />
    </div>
  );
}

function SubscribeCard({ externalId }: { externalId: string }) {
  const canWrite = useHasRole("write");
  const mutation = useSubscribe(externalId);
  const form = useForm<SubscribeForm>({
    resolver: zodResolver(subscribeSchema),
    defaultValues: { plan_key: "", seats: "" },
  });

  const submit = form.handleSubmit(async (values) => {
    try {
      await mutation.mutateAsync({
        plan_key: values.plan_key,
        seats: values.seats === "" ? 0 : Number(values.seats),
      });
      toast.success("Subscription started");
    } catch {
      // surfaced below
    }
  });

  return (
    <div className="space-y-4">
      <EmptyState
        icon={CreditCard}
        title="No subscription"
        description="This customer has no Stripe subscription mirrored yet. Subscribe them to one of your plans below."
      />
      <Card className="mx-auto w-full max-w-sm">
        <CardHeader>
          <CardTitle>Subscribe to a plan</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={(event) => void submit(event)} className="space-y-2.5">
            <FormField
              label="Plan key"
              error={form.formState.errors.plan_key?.message}
              hint="The key of a plan you created under Subscriptions (e.g. pro-monthly)."
            >
              {(id) => <Input id={id} {...form.register("plan_key")} autoFocus />}
            </FormField>
            <FormField
              label="Seats"
              error={form.formState.errors.seats?.message}
              hint="0 for plans without per-seat pricing."
            >
              {(id) => <Input id={id} inputMode="numeric" {...form.register("seats")} />}
            </FormField>
            {mutation.error != null && (
              <p className="text-[12px] text-danger-dark" role="alert">
                {problemMessage(mutation.error)}
              </p>
            )}
            <Button type="submit" size="sm" disabled={mutation.isPending || !canWrite}>
              {mutation.isPending ? "Working…" : "Subscribe"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

function ActiveSubscriptionCard({
  subscription,
  externalId,
}: {
  subscription: StripeSubscriptionOut;
  externalId: string;
}) {
  const isAdmin = useHasRole("admin");
  const pause = usePauseSubscription(externalId);
  const resume = useResumeSubscription(externalId);
  const cancel = useCancelSubscription(externalId);
  const setSeats = useSetSeats(externalId);
  const [cancelOpen, setCancelOpen] = React.useState(false);
  const [cancelImmediately, setCancelImmediately] = React.useState(false);
  const adminTitle = isAdmin ? undefined : "Requires the Admin role";

  const seatsForm = useForm<SeatsForm>({
    resolver: zodResolver(seatsSchema),
    defaultValues: { seats: "" },
  });

  const run = async (action: () => Promise<unknown>, message: string) => {
    try {
      await action();
      toast.success(message);
    } catch (error) {
      toast.error(problemMessage(error));
    }
  };

  const submitSeats = seatsForm.handleSubmit((values) =>
    run(
      () => setSeats.mutateAsync(Number(values.seats)),
      "Seat count updated — Stripe syncs the full live count",
    ),
  );

  const confirmCancel = async () => {
    await run(
      () => cancel.mutateAsync(!cancelImmediately),
      cancelImmediately
        ? "Subscription canceled immediately"
        : "Subscription will cancel at the period end",
    );
    setCancelOpen(false);
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          Subscription
          <Badge variant="outline">{subscriptionStatusLabel(subscription.status)}</Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <DetailList
          items={[
            { label: "Product", value: subscription.stripe_product_name },
            {
              label: "Amount",
              value: `${formatMicros(subscription.amount_micros, subscription.currency)} · ${planIntervalLabel(subscription.interval)}`,
            },
            {
              label: "Current period",
              value: `${formatShortDate(subscription.current_period_start)} → ${formatShortDate(subscription.current_period_end)}`,
            },
            {
              label: "Stripe subscription",
              value: subscription.stripe_subscription_id,
              mono: true,
            },
            { label: "Last synced", value: formatDate(subscription.last_synced_at) },
          ]}
        />
        <div className="flex flex-wrap items-center gap-2">
          {subscription.status === "paused" ? (
            <Button
              size="sm"
              variant="outline"
              disabled={resume.isPending || !isAdmin}
              title={adminTitle}
              onClick={() =>
                void run(
                  () => resume.mutateAsync(),
                  "Billing resumed — any pending cancel is cleared too",
                )
              }
            >
              {resume.isPending ? "Working…" : "Resume"}
            </Button>
          ) : (
            <Button
              size="sm"
              variant="outline"
              disabled={pause.isPending || !isAdmin}
              title={adminTitle}
              onClick={() =>
                void run(
                  () => pause.mutateAsync(),
                  "Collection paused — the subscription stays active but stops billing",
                )
              }
            >
              {pause.isPending ? "Working…" : "Pause"}
            </Button>
          )}
          <Button
            size="sm"
            variant="destructive"
            onClick={() => {
              setCancelImmediately(false);
              setCancelOpen(true);
            }}
            disabled={cancel.isPending || !isAdmin}
            title={adminTitle}
          >
            Cancel…
          </Button>
        </div>
        <form
          onSubmit={(event) => void submitSeats(event)}
          className="flex items-end gap-2"
        >
          <FormField
            label="Seats"
            error={seatsForm.formState.errors.seats?.message}
            className="w-32"
          >
            {(id) => <Input id={id} inputMode="numeric" {...seatsForm.register("seats")} />}
          </FormField>
          <Button
            type="submit"
            size="sm"
            variant="outline"
            disabled={setSeats.isPending || !isAdmin}
            title={adminTitle}
          >
            {setSeats.isPending ? "Working…" : "Set seats"}
          </Button>
        </form>
      </CardContent>

      <ConfirmDialog
        open={cancelOpen}
        onOpenChange={setCancelOpen}
        title="Cancel subscription?"
        destructive={cancelImmediately}
        description={
          <span className="space-y-2">
            <span className="block">
              {cancelImmediately
                ? "The subscription ends NOW — access stops and no further invoices are raised. This cannot be undone from here."
                : "The subscription stays active until the end of the current period, then ends. You can resume before then to clear the pending cancel."}
            </span>
            <label className="flex items-center gap-2 text-[12px]">
              <input
                type="checkbox"
                checked={cancelImmediately}
                onChange={(event) => setCancelImmediately(event.target.checked)}
              />
              Cancel immediately instead of at period end
            </label>
          </span>
        }
        confirmLabel={cancelImmediately ? "Cancel immediately" : "Cancel at period end"}
        onConfirm={() => void confirmCancel()}
        pending={cancel.isPending}
      />
    </Card>
  );
}

function InvoicesCard({ customerId }: { customerId: string }) {
  const list = useSubscriptionInvoices(customerId);

  return (
    <Card>
      <CardHeader>
        <CardTitle>Paid invoices</CardTitle>
      </CardHeader>
      <CardContent>
        {list.isInitialLoading ? (
          <Skeleton className="h-24 w-full" />
        ) : list.isError ? (
          <ErrorCard error={list.error} onRetry={() => void list.refetch()} />
        ) : list.rows.length === 0 ? (
          <EmptyState
            title="No paid invoices yet"
            description="Paid subscription invoices mirrored from Stripe appear here."
          />
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Period</TableHead>
                  <TableHead className="text-right">Amount paid</TableHead>
                  <TableHead>Paid at</TableHead>
                  <TableHead>Stripe invoice</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {list.rows.map((invoice) => (
                  <TableRow key={invoice.id}>
                    <TableCell className="whitespace-nowrap text-[12px]">
                      {formatShortDate(invoice.period_start)} →{" "}
                      {formatShortDate(invoice.period_end)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatMicros(invoice.amount_paid_micros, invoice.currency)}
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-[12px]">
                      {formatDate(invoice.paid_at)}
                    </TableCell>
                    <TableCell className="font-mono text-[12px]">
                      {invoice.stripe_invoice_id}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <LoadMore
              shownCount={list.rows.length}
              hasMore={list.hasMore}
              isFetchingNextPage={list.isFetchingNextPage}
              onLoadMore={list.fetchNextPage}
              noun="invoices"
            />
          </div>
        )}
      </CardContent>
    </Card>
  );
}
