import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Plus } from "lucide-react";
import {
  Section,
  LoadingRows,
  ErrorInline,
} from "@/components/shared/data-states";
import { EmptyState } from "@/components/shared/empty-state";
import { StatusBadge } from "@/components/shared/status-badge";
import { CursorPagerControls } from "@/components/shared/cursor-pager";
import { ConfirmDialog } from "@/components/shared/confirm-dialog";
import { FormField } from "@/components/shared/form-field";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogClose,
  DialogTrigger,
} from "@/components/ui/dialog";
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
import { formatMicros, formatShortDate } from "@/lib/format";
import { useGrants, useCreateGrant, useVoidGrant } from "../api/queries";
import { grantSchema, type GrantValues } from "../lib/schema";

export function CustomerGrantsSection({ customerId }: { customerId: string }) {
  const grants = useGrants(customerId);
  const voidGrant = useVoidGrant(customerId);

  return (
    <Section
      title="Grants"
      description="Promotional or goodwill credit that draws down before paid balance."
      actions={<CreateGrantDialog customerId={customerId} />}
    >
      {grants.isLoading ? (
        <LoadingRows rows={3} />
      ) : grants.isError ? (
        <ErrorInline error={grants.error} onRetry={grants.refetch} />
      ) : grants.items.length === 0 ? (
        <EmptyState title="No grants" description="Issue a grant to give this customer credit." />
      ) : (
        <div className="space-y-3">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Kind</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Remaining</TableHead>
                <TableHead className="text-right">Granted</TableHead>
                <TableHead>Expires</TableHead>
                <TableHead className="w-8" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {grants.items.map((g) => (
                <TableRow key={g.id}>
                  <TableCell><StatusBadge value={g.kind} tone="neutral" /></TableCell>
                  <TableCell><StatusBadge value={g.status} /></TableCell>
                  <TableCell className="text-right tabular-nums">
                    {formatMicros(g.remaining_micros, g.currency)}
                  </TableCell>
                  <TableCell className="text-right tabular-nums text-muted-foreground">
                    {formatMicros(g.granted_micros, g.currency)}
                  </TableCell>
                  <TableCell className="text-muted-foreground">
                    {g.expires_at ? formatShortDate(g.expires_at) : "—"}
                  </TableCell>
                  <TableCell>
                    {g.remaining_micros > 0 && g.status === "active" && (
                      <ConfirmDialog
                        destructive
                        title="Void this grant?"
                        description="The remaining balance will be removed. This can't be undone."
                        confirmLabel="Void grant"
                        onConfirm={() => voidGrant.mutateAsync(g.id)}
                        trigger={<Button variant="ghost" size="xs">Void</Button>}
                      />
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          <CursorPagerControls pager={grants} />
        </div>
      )}
    </Section>
  );
}

function CreateGrantDialog({ customerId }: { customerId: string }) {
  const [open, setOpen] = useState(false);
  const create = useCreateGrant(customerId);
  const form = useForm<GrantValues>({
    resolver: zodResolver(grantSchema),
    defaultValues: { kind: "promotional", amount: 0, description: "" },
  });
  const { errors } = form.formState;

  const onSubmit = form.handleSubmit(async (v) => {
    await create.mutateAsync({
      kind: v.kind,
      amount_micros: Math.round(v.amount * 1_000_000),
      expires_in_days: v.expires_in_days,
      description: v.description ?? "",
      idempotency_key: crypto.randomUUID(),
    });
    setOpen(false);
    form.reset({ kind: "promotional", amount: 0, description: "" });
  });

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger render={<Button size="sm" variant="outline" />}>
        <Plus />
        Issue grant
      </DialogTrigger>
      <DialogContent>
        <form onSubmit={onSubmit}>
          <DialogHeader>
            <DialogTitle>Issue grant</DialogTitle>
            <DialogDescription>Credit that draws down before the paid balance.</DialogDescription>
          </DialogHeader>
          <div className="mt-4 flex flex-col gap-4">
            <FormField label="Kind" error={errors.kind?.message}>
              {(id) => <Input id={id} placeholder="promotional" {...form.register("kind")} />}
            </FormField>
            <FormField label="Amount (USD)" error={errors.amount?.message}>
              {(id) => <Input id={id} type="number" min={0} step={0.01} {...form.register("amount", { valueAsNumber: true })} />}
            </FormField>
            <FormField label="Expires in (days)" hint="Optional" error={errors.expires_in_days?.message}>
              {(id) => <Input id={id} type="number" min={1} {...form.register("expires_in_days", { valueAsNumber: true, setValueAs: (v) => (v === "" || Number.isNaN(v) ? undefined : Number(v)) })} />}
            </FormField>
            <FormField label="Description" hint="Optional" error={errors.description?.message}>
              {(id) => <Input id={id} {...form.register("description")} />}
            </FormField>
          </div>
          <DialogFooter className="mt-2">
            <DialogClose render={<Button variant="outline" type="button" disabled={create.isPending} />}>Cancel</DialogClose>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? "Issuing…" : "Issue grant"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
