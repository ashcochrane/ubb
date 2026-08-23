import * as React from "react";

import { FormField } from "@/components/shared/form-field";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";

/**
 * When a declared change takes effect — off for "now", on for a date.
 *
 * ⚠ **ONE CONTROL AND ONE PARSE, BECAUSE THE SECOND COPY HAD A BUG.** Two
 * screens declare a dated change — a change to a book, and a customer's own
 * deal — and both were written with their own switch, their own
 * `datetime-local` input and their own ISO derivation. Only one of the two
 * guarded `Number.isNaN` on the parse, so on the other a half-typed date
 * reached `new Date(...).toISOString()` and threw `RangeError` rather than
 * being ignored. That is exactly what the smell is for: a shape copied twice
 * diverges, and it diverges where nobody is looking.
 *
 * ⚠ **AN UNPARSEABLE INSTANT MEANS "NOT STATED", NOT "NOW".** `undefined` is
 * what the body sends for an immediate change, so a caller cannot tell the two
 * apart from the value alone — which is right: a tenant mid-way through typing
 * a date has not asked for anything yet, and the submit button is what decides
 * whether that is a change they meant to make immediately. The 366-day horizon
 * and every other bound stay the server's to enforce; this control refuses
 * nothing, so a refusal a tenant sees is always the platform's own named one.
 */
export function EffectiveInstant({
  label,
  hint,
  value,
  onChange,
}: {
  /** The switch's label, which differs by what is being dated. */
  label: string;
  hint: string;
  /** The local `datetime-local` value, held by the caller with its form state. */
  value: string;
  onChange: (next: string) => void;
}) {
  const dated = value !== "";
  const [showing, setShowing] = React.useState(false);
  const open = dated || showing;

  return (
    <div className="space-y-2">
      <div className="flex items-start gap-2.5">
        <Switch
          checked={open}
          onCheckedChange={(next) => {
            setShowing(next);
            if (!next) onChange("");
          }}
          aria-label={label}
        />
        <div>
          <p className="text-[13px] font-medium text-text-primary">{label}</p>
          <p className="text-xs text-muted-foreground">{hint}</p>
        </div>
      </div>
      {open && (
        <FormField label="Takes effect">
          {(id) => (
            <Input
              id={id}
              type="datetime-local"
              className="w-[240px]"
              value={value}
              onChange={(event) => onChange(event.target.value)}
            />
          )}
        </FormField>
      )}
    </div>
  );
}
