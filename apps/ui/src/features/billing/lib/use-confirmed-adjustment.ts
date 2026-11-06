// Confirm-dialog state + replay-safe idempotency key, shared by the
// credit/debit ledger-adjustment forms.

import { useRef, useState } from "react";

import type { DebitCreditResponse } from "../api/types";

/** The route's answer, beside the platform Customer UUID it was asked about (F-13). */
export type AdjustmentResult = DebitCreditResponse & { customer_id: string };

export function useConfirmedAdjustment() {
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [lastResult, setLastResult] = useState<AdjustmentResult | null>(null);
  // Generated when the confirm dialog opens; REUSED on retry after a failure
  // (replay-safe by design) and replaced only after a success.
  const idempotencyKey = useRef<string | null>(null);

  const openConfirm = () => {
    idempotencyKey.current ??= crypto.randomUUID();
    setConfirmOpen(true);
  };
  const onSuccessReset = () => {
    idempotencyKey.current = null;
    setConfirmOpen(false);
  };
  return {
    confirmOpen,
    setConfirmOpen,
    lastResult,
    setLastResult,
    idempotencyKey,
    openConfirm,
    onSuccessReset,
  };
}
