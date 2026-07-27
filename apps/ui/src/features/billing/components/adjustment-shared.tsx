// Shared field components for the credit/debit ledger-adjustment forms.
// (The companion hook lives in ../lib/use-confirmed-adjustment.)

import type { UseFormRegisterReturn } from "react-hook-form";

import { FormField } from "@/components/shared/form-field";
import { Input } from "@/components/ui/input";
import { formatMicros } from "@/lib/format";

import type { AdjustmentResult } from "../lib/use-confirmed-adjustment";

/** Visible, durable success confirmation (toasts vanish; money shouldn't). */
export function LastResultLine({
  result,
  currency,
}: {
  result: AdjustmentResult | null;
  currency: string;
}) {
  if (!result) return null;
  return (
    <p className="text-[12px] text-text-secondary">
      Done — <span className="font-mono">{result.external_id}</span> balance is now{" "}
      <span className="font-medium text-text-primary">
        {formatMicros(result.new_balance_micros, currency)}
      </span>{" "}
      (transaction <span className="font-mono">{result.transaction_id}</span>).
    </p>
  );
}

// The fields both forms share, wired via plain register-return props so the
// two differently-typed forms can reuse them without casts.
type RegisteredInput = UseFormRegisterReturn;

export function AdjustmentSharedFields({
  currency,
  isAdmin,
  customer,
  amount,
  reference,
  errors,
}: {
  currency: string;
  isAdmin: boolean;
  customer: RegisteredInput;
  amount: RegisteredInput;
  reference: RegisteredInput;
  errors: { customer?: string; amount?: string; reference?: string };
}) {
  return (
    <>
      <FormField
        label="Customer external ID"
        error={errors.customer}
        hint="The ID your systems use for this customer (as sent in usage events) — not the UBB UUID."
      >
        {(id) => <Input id={id} className="font-mono" disabled={!isAdmin} {...customer} />}
      </FormField>
      <FormField label={`Amount (${currency.toUpperCase()})`} error={errors.amount}>
        {(id) => (
          <Input
            id={id}
            type="number"
            min={0}
            step="0.01"
            inputMode="decimal"
            disabled={!isAdmin}
            {...amount}
          />
        )}
      </FormField>
      <FormField
        label="Reference"
        error={errors.reference}
        hint="Stored on the ledger entry, e.g. a support ticket number."
      >
        {(id) => <Input id={id} disabled={!isAdmin} {...reference} />}
      </FormField>
    </>
  );
}

export function OptionalFields({
  isAdmin,
  actor,
  reasonCode,
  errors,
}: {
  isAdmin: boolean;
  actor: RegisteredInput;
  reasonCode: RegisteredInput;
  errors: { actor?: string; reasonCode?: string };
}) {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      <FormField label="Actor (optional)" error={errors.actor} hint="Who is making this change.">
        {(id) => <Input id={id} disabled={!isAdmin} {...actor} />}
      </FormField>
      <FormField
        label="Reason code (optional)"
        error={errors.reasonCode}
        hint="Short code for reporting, up to 32 characters."
      >
        {(id) => <Input id={id} disabled={!isAdmin} {...reasonCode} />}
      </FormField>
    </div>
  );
}
