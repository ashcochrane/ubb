// src/features/customers/components/orphaned-events-section.tsx
import { useState } from "react";
import {
  Dialog,
  DialogTrigger,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogClose,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { useDismissOrphans } from "../api/queries";
import type { CustomerMapping, OrphanedIdentifier } from "../api/types";
import { OrphanRow } from "./orphan-row";

interface OrphanedEventsSectionProps {
  orphans: OrphanedIdentifier[];
  customers: CustomerMapping[];
}

export function OrphanedEventsSection({
  orphans,
  customers,
}: OrphanedEventsSectionProps) {
  const dismissMutation = useDismissOrphans();
  const [dismissOpen, setDismissOpen] = useState(false);
  const totalEvents = orphans.reduce((sum, o) => sum + o.eventCount, 0);

  if (orphans.length === 0) return null;

  return (
    <div>
      <div className="mb-3">
        <h2 className="text-[15px] font-bold text-text-primary">Unrecognised SDK identifiers</h2>
        <p className="mt-1 text-[13px] text-text-secondary">
          These customer IDs appeared in SDK events but don&apos;t match any
          mapping. Either map them to an existing Stripe customer, or check your
          code for typos.
        </p>
      </div>

      <div className="mb-2.5 flex items-center justify-between rounded-md border border-red-border bg-red-light px-3.5 py-2.5">
        <span className="text-[12px] font-semibold text-red-text">
          {orphans.length} unknown identifier{orphans.length !== 1 && "s"} (
          {totalEvents} events)
        </span>
        <Dialog open={dismissOpen} onOpenChange={setDismissOpen}>
          <DialogTrigger className="rounded-full border border-red-border bg-bg-surface px-3 py-1 text-[11px] font-medium text-red-text hover:bg-red-light">
            Dismiss all
          </DialogTrigger>
          <DialogContent showCloseButton={false}>
            <DialogHeader>
              <DialogTitle>Dismiss all orphaned identifiers?</DialogTitle>
              <DialogDescription>
                This will dismiss {orphans.length} unrecognised SDK identifiers
                and {totalEvents} unattributed events. This action cannot be
                undone.
              </DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <DialogClose render={<Button variant="outline" />}>
                Cancel
              </DialogClose>
              <Button
                variant="destructive"
                onClick={() => {
                  dismissMutation.mutate(undefined, {
                    onSuccess: () => setDismissOpen(false),
                  });
                }}
                disabled={dismissMutation.isPending}
              >
                {dismissMutation.isPending ? "Dismissing..." : "Dismiss all"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      <div className="overflow-hidden rounded-md border border-border bg-bg-surface">
        <table className="w-full border-collapse text-[13px]">
          <thead>
            <tr className="border-b border-border bg-bg-subtle">
              <th className="px-3.5 py-2 text-left text-[10px] font-bold uppercase tracking-[0.06em] text-text-muted">
                SDK identifier received
              </th>
              <th className="px-3.5 py-2 text-left text-[10px] font-bold uppercase tracking-[0.06em] text-text-muted">
                First seen
              </th>
              <th className="px-3.5 py-2 text-right text-[10px] font-bold uppercase tracking-[0.06em] text-text-muted">
                Events
              </th>
              <th className="px-3.5 py-2 text-right text-[10px] font-bold uppercase tracking-[0.06em] text-text-muted">
                Unattributed cost
              </th>
              <th className="px-3.5 py-2 text-left text-[10px] font-bold uppercase tracking-[0.06em] text-text-muted">
                Assign to Stripe customer
              </th>
            </tr>
          </thead>
          <tbody>
            {orphans.map((orphan) => (
              <OrphanRow key={orphan.id} orphan={orphan} customers={customers} />
            ))}
          </tbody>
        </table>
      </div>

      <p className="mt-2.5 text-[11px] leading-relaxed text-text-muted">
        When you assign an orphaned identifier, the existing events are
        retroactively attributed to that Stripe customer. Future events with this
        identifier will also be mapped automatically.
      </p>
    </div>
  );
}
