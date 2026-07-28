// Confirm-dialog state + replay-safe idempotency key, shared by the
// credit/debit ledger-adjustment forms.

import { useRef, useState } from "react";

import type { DebitCreditResponse } from "../api/types";

export type AdjustmentResult = DebitCreditResponse & { external_id: string };

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
