import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import {
  Section,
  DetailGrid,
  DetailRow,
  LoadingRows,
  ErrorInline,
} from "@/components/shared/data-states";
import { EmptyState } from "@/components/shared/empty-state";
import { StatusBadge } from "@/components/shared/status-badge";
import { CursorPagerControls } from "@/components/shared/cursor-pager";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { FormField } from "@/components/shared/form-field";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from "@/components/ui/table";
import { formatMicros, formatDate, formatShortDate, humanizeLabel } from "@/lib/format";
import {
  useSubscription,
  useSubscriptionInvoices,
  useSubscribeCustomer,
  useSetSeats,
  useCancelSubscription,
  usePauseSubscription,
  useResumeSubscription,
} from "../api/queries";
import { subscribeSchema, type SubscribeValues, seatsSchema, type SeatsValues } from "../lib/schema";

export function CustomerSubscriptionTab({
  customerId,
  externalId,
}: {
  customerId: string;
  externalId: string | null;
}) {
  const sub = useSubscription(customerId);
  const invoices = useSubscriptionInvoices(customerId);

  return (
    <div className="space-y-6">
      <Section title="Subscription">
        {sub.isLoading ? (
          <LoadingRows rows={2} />
        ) : sub.isError || !sub.data ? (
          <EmptyState
            title="No active subscription"
            description="This customer has no synced Stripe subscription. Start one below."
          />
        ) : (
          <DetailGrid>
            <DetailRow label="Status"><StatusBadge value={sub.data.status} /></DetailRow>
            <DetailRow label="Product">{sub.data.stripe_product_name}</DetailRow>
            <DetailRow label="Amount">
              {formatMicros(sub.data.amount_micros, sub.data.currency)} / {humanizeLabel(sub.data.interval)}
            </DetailRow>
            <DetailRow label="Current period">
              {formatShortDate(sub.data.current_period_start)} → {formatShortDate(sub.data.current_period_end)}
            </DetailRow>
            <DetailRow label="Last synced">{formatDate(sub.data.last_synced_at)}</DetailRow>
          </DetailGrid>
        )}
      </Section>

      {externalId ? (
        <LifecycleActions customerId={customerId} externalId={externalId} hasSub={Boolean(sub.data)} />
      ) : (
        <Alert>
          <AlertTitle>Lifecycle actions unavailable</AlertTitle>
          <AlertDescription>
            Managing the subscription needs the customer's external ID, which is resolved from margin data
            (billing tenants). It isn't available for this customer.
          </AlertDescription>
        </Alert>
      )}

      <Section title="Subscription invoices">
        {invoices.isLoading ? (
          <LoadingRows rows={3} />
        ) : invoices.isError ? (
          <ErrorInline error={invoices.error} onRetry={invoices.refetch} />
        ) : invoices.items.length === 0 ? (
          <EmptyState title="No subscription invoices" />
        ) : (
          <div className="space-y-3">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Invoice</TableHead>
                  <TableHead className="text-right">Amount paid</TableHead>
                  <TableHead>Period</TableHead>
                  <TableHead>Paid</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {invoices.items.map((inv) => (
                  <TableRow key={inv.id}>
                    <TableCell className="font-mono text-xs">{inv.stripe_invoice_id}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatMicros(inv.amount_paid_micros, inv.currency)}
                    </TableCell>
                    <TableCell className="text-muted-foreground">
                      {formatShortDate(inv.period_start)} → {formatShortDate(inv.period_end)}
                    </TableCell>
                    <TableCell className="text-muted-foreground">{formatShortDate(inv.paid_at)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
            <CursorPagerControls pager={invoices} />
          </div>
        )}
      </Section>
    </div>
  );
}

function LifecycleActions({
  customerId,
  externalId,
  hasSub,
}: {
  customerId: string;
  externalId: string;
  hasSub: boolean;
}) {
  const subscribe = useSubscribeCustomer(customerId, externalId);
  const setSeats = useSetSeats(customerId, externalId);
  const cancel = useCancelSubscription(customerId, externalId);
  const pause = usePauseSubscription(customerId, externalId);
  const resume = useResumeSubscription(customerId, externalId);

  const subForm = useForm<SubscribeValues>({
    resolver: zodResolver(subscribeSchema),
    defaultValues: { plan_key: "", seats: 0 },
  });
  const seatsForm = useForm<SeatsValues>({
    resolver: zodResolver(seatsSchema),
    defaultValues: { seats: 1 },
  });
  const [atPeriodEnd, setAtPeriodEnd] = useState(true);

  return (
    <Section title="Manage subscription" description="Start, adjust, pause, resume, or cancel.">
      <div className="space-y-6">
        <form
          onSubmit={subForm.handleSubmit((v) => subscribe.mutate({ plan_key: v.plan_key, seats: v.seats }))}
          className="flex flex-wrap items-end gap-3"
        >
          <FormField label="Plan key" error={subForm.formState.errors.plan_key?.message}>
            {(id) => <Input id={id} placeholder="pro" {...subForm.register("plan_key")} />}
          </FormField>
          <FormField label="Seats" error={subForm.formState.errors.seats?.message}>
            {(id) => <Input id={id} type="number" min={0} className="w-24" {...subForm.register("seats", { valueAsNumber: true })} />}
          </FormField>
          <Button type="submit" disabled={subscribe.isPending}>
            {hasSub ? "Change plan" : "Subscribe"}
          </Button>
        </form>

        <form
          onSubmit={seatsForm.handleSubmit((v) => setSeats.mutate({ seats: v.seats }))}
          className="flex items-end gap-3"
        >
          <FormField label="Set seats" error={seatsForm.formState.errors.seats?.message}>
            {(id) => <Input id={id} type="number" min={0} className="w-24" {...seatsForm.register("seats", { valueAsNumber: true })} />}
          </FormField>
          <Button type="submit" variant="outline" disabled={setSeats.isPending}>Update seats</Button>
        </form>

        <div className="flex flex-wrap items-center gap-2 border-t border-border pt-4">
          <Button variant="outline" size="sm" disabled={pause.isPending} onClick={() => pause.mutate()}>Pause</Button>
          <Button variant="outline" size="sm" disabled={resume.isPending} onClick={() => resume.mutate()}>Resume</Button>
          <label className="ml-2 flex items-center gap-1.5 text-xs text-muted-foreground">
            <input type="checkbox" className="size-3.5 accent-foreground" checked={atPeriodEnd} onChange={(e) => setAtPeriodEnd(e.target.checked)} />
            Cancel at period end
          </label>
          <ConfirmDialog
            destructive
            title="Cancel this subscription?"
            description={atPeriodEnd ? "It will remain active until the end of the current period." : "It will be canceled immediately."}
            confirmLabel="Cancel subscription"
            onConfirm={() => cancel.mutateAsync({ at_period_end: atPeriodEnd })}
            trigger={<Button variant="destructive" size="sm">Cancel subscription</Button>}
          />
        </div>
      </div>
    </Section>
  );
}
