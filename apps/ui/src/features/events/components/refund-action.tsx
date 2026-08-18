// "Refund this charge" — billing product, Admin floor. The idempotency key
// is minted when the dialog opens and REUSED across retries (replay-safe);
// a fresh key is only minted after a successful refund.

import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";

import { problemMessage } from "@/api/problem";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useHasRole } from "@/hooks/use-current-role";
import { formatMicros } from "@/lib/format";
import { toastSuccess } from "@/lib/mutations";

import { useRefundUsage } from "../api/queries";
import type { UsageEventDetail } from "../api/types";
import { formatEventMicros } from "../lib/money";

const refundSchema = z.object({
  reason: z.string().max(500, "Keep the reason under 500 characters."),
});

type RefundForm = z.infer<typeof refundSchema>;

export function RefundAction({
  detail,
  customerId,
}: {
  detail: UsageEventDetail;
  customerId: string;
}) {
  const [open, setOpen] = useState(false);
  const [idempotencyKey, setIdempotencyKey] = useState<string | null>(null);
  const isAdmin = useHasRole("admin");
  const refund = useRefundUsage(customerId);
  // Per-event amount — keep sub-cent precision so a micro-priced charge
  // never shows as a rounded-up refund; the balance toast stays 2-decimal.
  //
  // ⚠ `null` WHERE UBB COULD NOT RESOLVE A PRICE (#351), and there is nothing
  // to refund then — the server refuses such a refund with its own code. The
  // affordance is hidden rather than shown against a zero, which would offer a
  // tenant a refund of nothing and take a round trip to say so.
  const billed = detail.billed_cost_micros ?? null;
  const amount =
    billed === null ? null : formatEventMicros(billed, detail.currency);

  const form = useForm<RefundForm>({
    resolver: zodResolver(refundSchema),
    defaultValues: { reason: "" },
  });

  const openDialog = () => {
    // Reuse the key while a failed attempt is pending retry — replay-safe.
    setIdempotencyKey((key) => key ?? crypto.randomUUID());
    setOpen(true);
  };

  const submit = form.handleSubmit((values) => {
    if (idempotencyKey === null) return;
    refund.mutate(
      {
        usage_event_id: detail.id,
        idempotency_key: idempotencyKey,
        reason: values.reason,
      },
      {
        onSuccess: (result) => {
          toastSuccess(
            "Refund issued",
            `The wallet balance is now ${formatMicros(result.balance_micros, detail.currency)}.`,
          );
          setOpen(false);
          setIdempotencyKey(null);
          form.reset();
        },
      },
    );
  });

  // There is no charge to refund where UBB never resolved a price, so the
  // affordance is not offered at all (#351).
  if (amount === null) return null;

  return (
    <>
      <span title={isAdmin ? undefined : "Requires the Admin role"}>
        <Button
          variant="outline"
          size="sm"
          onClick={openDialog}
          disabled={!isAdmin || refund.isSuccess}
        >
          {refund.isSuccess ? "Refunded" : "Refund this charge"}
        </Button>
      </span>
      <Dialog
        open={open}
        onOpenChange={(next) => {
          if (!refund.isPending) setOpen(next);
        }}
      >
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Refund this charge?</DialogTitle>
            <DialogDescription>
              Returns {amount} to the customer's wallet. Portions that were
              funded by promo credit go back as promo credit — they never
              become withdrawable cash.
            </DialogDescription>
          </DialogHeader>
          <form onSubmit={submit} className="space-y-3">
            <div className="space-y-1.5">
              <Label htmlFor="refund-reason">Reason (optional)</Label>
              <Textarea
                id="refund-reason"
                rows={3}
                placeholder="Why is this charge being refunded?"
                {...form.register("reason")}
              />
              {form.formState.errors.reason ? (
                <p className="text-[12px] text-red-text">
                  {form.formState.errors.reason.message}
                </p>
              ) : (
                <p className="text-[11px] text-text-muted">
                  Kept with the refund on the wallet ledger and audit trail.
                </p>
              )}
            </div>
            {refund.isError && (
              <p className="text-[12px] text-red-text">
                {problemMessage(refund.error)}
              </p>
            )}
            <DialogFooter>
              <Button
                type="button"
                variant="outline"
                onClick={() => setOpen(false)}
                disabled={refund.isPending}
              >
                Cancel
              </Button>
              <Button type="submit" disabled={refund.isPending}>
                {refund.isPending ? "Working…" : `Refund ${amount}`}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </>
  );
}
