// Credit grants: list with status filter, create (expiry is expires_at XOR
// expires_in_days — made structural by the expiry-mode radio), and void with
// a destructive confirm.

import * as React from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { Gift, Info } from "lucide-react";
import { useForm } from "react-hook-form";
import { toast } from "sonner";

import { problemMessage } from "@/api/problem";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { DisabledHint } from "@/components/shared/disabled-hint";
import { EmptyState } from "@/components/shared/empty-state";
import { ErrorCard } from "@/components/shared/error-card";
import { FormField } from "@/components/shared/form-field";
import { LoadMore } from "@/components/shared/load-more";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
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
import { useIsPostpaid, useTenantCurrency } from "@/hooks/use-tenant-config";
import { formatDate, formatMicros } from "@/lib/format";
import { grantKindLabel, grantSourceLabel, grantStatusLabel } from "@/lib/labels";

import { useCreateGrant, useGrantsList, useVoidGrant } from "../api/queries";
import type { GrantOut } from "../api/types";
import { toMicros } from "../lib/helpers";
import { grantSchema, type GrantForm } from "../lib/schemas";

const STATUS_FILTERS = ["all", "active", "depleted", "expired", "voided"];

export function GrantsSection({ customerId }: { customerId: string }) {
  const currency = useTenantCurrency();
  const isAdmin = useHasRole("admin");
  const postpaid = useIsPostpaid();
  const [status, setStatus] = React.useState("all");
  const [createOpen, setCreateOpen] = React.useState(false);
  const [voidTarget, setVoidTarget] = React.useState<GrantOut | null>(null);
  const list = useGrantsList(
    customerId,
    status === "all" ? undefined : status,
    !postpaid,
  );
  const voidMutation = useVoidGrant(customerId);

  const confirmVoid = async () => {
    if (!voidTarget) return;
    try {
      await voidMutation.mutateAsync(voidTarget.id);
      toast.success("Grant voided");
      setVoidTarget(null);
    } catch (error) {
      toast.error(problemMessage(error));
    }
  };

  if (postpaid) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Credit grants</CardTitle>
        </CardHeader>
        <CardContent>
          <Alert>
            <Info />
            <AlertDescription>
              Credit grants aren't used under postpaid billing — there's no
              prepaid wallet for a grant to top up. Usage is invoiced through
              Stripe at period close instead; switch to prepaid in Settings →
              Billing to use grants again.
            </AlertDescription>
          </Alert>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Credit grants</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <Select value={status} onValueChange={(value) => setStatus(value ?? "all")}>
            <SelectTrigger className="h-8 text-[12px]" aria-label="Grant status filter">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {STATUS_FILTERS.map((value) => (
                <SelectItem key={value} value={value}>
                  {value === "all" ? "All statuses" : grantStatusLabel(value)}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <div className="flex items-center gap-2">
            <DisabledHint disabled={!isAdmin} hint="Requires the Admin role.">
              <Button size="sm" onClick={() => setCreateOpen(true)} disabled={!isAdmin}>
                Create grant
              </Button>
            </DisabledHint>
          </div>
        </div>

        {list.isInitialLoading ? (
          <Skeleton className="h-28 w-full" />
        ) : list.isError ? (
          <ErrorCard error={list.error} onRetry={() => void list.refetch()} />
        ) : list.rows.length === 0 ? (
          <EmptyState
            icon={Gift}
            title={status === "all" ? "No grants yet" : `No ${status} grants`}
            description="Grants are expiring (or promo) credit lots on the billing owner's wallet."
            action={
              isAdmin
                ? { label: "Create grant", onClick: () => setCreateOpen(true) }
                : undefined
            }
          />
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Kind</TableHead>
                  <TableHead className="text-right">Granted</TableHead>
                  <TableHead className="text-right">Remaining</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Source</TableHead>
                  <TableHead>Expires</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {list.rows.map((grant) => (
                  <TableRow key={grant.id}>
                    <TableCell>{grantKindLabel(grant.kind)}</TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatMicros(grant.granted_micros, currency)}
                    </TableCell>
                    <TableCell className="text-right tabular-nums">
                      {formatMicros(grant.remaining_micros, currency)}
                    </TableCell>
                    <TableCell>{grantStatusLabel(grant.status)}</TableCell>
                    <TableCell>{grantSourceLabel(grant.source)}</TableCell>
                    <TableCell className="whitespace-nowrap text-[12px]">
                      {grant.expires_at ? formatDate(grant.expires_at) : "Never"}
                    </TableCell>
                    <TableCell className="whitespace-nowrap text-[12px]">
                      {formatDate(grant.created_at)}
                    </TableCell>
                    <TableCell className="text-right">
                      {grant.status === "active" && (
                        <DisabledHint disabled={!isAdmin} hint="Requires the Admin role.">
                          <Button
                            variant="ghost"
                            size="xs"
                            onClick={() => setVoidTarget(grant)}
                            disabled={!isAdmin}
                          >
                            Void
                          </Button>
                        </DisabledHint>
                      )}
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
              noun="grants"
            />
          </div>
        )}
      </CardContent>

      <CreateGrantDialog
        customerId={customerId}
        open={createOpen}
        onOpenChange={setCreateOpen}
      />
      <ConfirmDialog
        open={voidTarget !== null}
        onOpenChange={(open) => {
          if (!open) setVoidTarget(null);
        }}
        title="Void this grant?"
        description={
          voidTarget
            ? `The remaining ${formatMicros(voidTarget.remaining_micros, currency)} is debited from the wallet (clamped so the balance never goes below zero) and the lot is retired. This can't be undone.`
            : ""
        }
        confirmLabel="Void grant"
        destructive
        onConfirm={() => void confirmVoid()}
        pending={voidMutation.isPending}
      />
    </Card>
  );
}

function CreateGrantDialog({
  customerId,
  open,
  onOpenChange,
}: {
  customerId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const currency = useTenantCurrency();
  const mutation = useCreateGrant(customerId);
  const [idempotencyKey, setIdempotencyKey] = React.useState(() => crypto.randomUUID());
  React.useEffect(() => {
    if (open) setIdempotencyKey(crypto.randomUUID());
  }, [open]);

  const form = useForm<GrantForm>({
    resolver: zodResolver(grantSchema),
    defaultValues: {
      amount: "",
      kind: "paid",
      expiry_mode: "none",
      expires_at: "",
      expires_in_days: "",
      description: "",
    },
  });
  const expiryMode = form.watch("expiry_mode");

  const submit = form.handleSubmit(async (values) => {
    try {
      await mutation.mutateAsync({
        amount_micros: toMicros(values.amount),
        kind: values.kind,
        idempotency_key: idempotencyKey,
        description: values.description,
        // XOR by construction: only the selected expiry mode's field is sent.
        expires_at:
          values.expiry_mode === "at"
            ? new Date(`${values.expires_at}T00:00:00Z`).toISOString()
            : null,
        expires_in_days:
          values.expiry_mode === "days" ? Number(values.expires_in_days) : null,
      });
      toast.success("Grant created");
      form.reset();
      onOpenChange(false);
    } catch {
      // surfaced below; retry reuses the idempotency key
    }
  });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle>Create credit grant</DialogTitle>
          <DialogDescription>
            Adds a credit lot to the billing owner's wallet. Promo credit can be
            spent but never withdrawn.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={(event) => void submit(event)} className="space-y-3">
          <div className="grid grid-cols-2 gap-2.5">
            <FormField
              label={`Amount (${currency.toUpperCase()})`}
              error={form.formState.errors.amount?.message}
            >
              {(id) => (
                <Input id={id} inputMode="decimal" {...form.register("amount")} autoFocus />
              )}
            </FormField>
            <FormField label="Kind">
              {() => (
                <Select
                  value={form.watch("kind")}
                  onValueChange={(value) => form.setValue("kind", value ?? "paid")}
                >
                  <SelectTrigger className="w-full" aria-label="Grant kind">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="paid">Paid</SelectItem>
                    <SelectItem value="promo">Promo</SelectItem>
                  </SelectContent>
                </Select>
              )}
            </FormField>
          </div>
          <FormField
            label="Expiry"
            hint="A grant expires by date OR after a number of days — never both."
          >
            {() => (
              <Select
                value={expiryMode}
                onValueChange={(value) => {
                  if (value === "none" || value === "at" || value === "days") {
                    form.setValue("expiry_mode", value);
                  }
                }}
              >
                <SelectTrigger className="w-full" aria-label="Expiry mode">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">Never expires</SelectItem>
                  <SelectItem value="at">On a date</SelectItem>
                  <SelectItem value="days">After N days</SelectItem>
                </SelectContent>
              </Select>
            )}
          </FormField>
          {expiryMode === "at" && (
            <FormField
              label="Expires at"
              error={form.formState.errors.expires_at?.message}
            >
              {(id) => <Input id={id} type="date" {...form.register("expires_at")} />}
            </FormField>
          )}
          {expiryMode === "days" && (
            <FormField
              label="Expires in days"
              error={form.formState.errors.expires_in_days?.message}
              hint="1–3650 days from now."
            >
              {(id) => (
                <Input id={id} inputMode="numeric" {...form.register("expires_in_days")} />
              )}
            </FormField>
          )}
          <FormField
            label="Description"
            error={form.formState.errors.description?.message}
          >
            {(id) => <Input id={id} {...form.register("description")} />}
          </FormField>
          {mutation.error != null && (
            <p className="text-[12px] text-danger-dark" role="alert">
              {problemMessage(mutation.error)}
            </p>
          )}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={mutation.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={mutation.isPending}>
              {mutation.isPending ? "Working…" : "Create grant"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
