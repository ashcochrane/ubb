import * as React from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";

import { ApiProblem, problemMessage } from "@/api/problem";
import { FormField } from "@/components/shared/form-field";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { useIsMeteringOnly, useTenantCurrency } from "@/hooks/use-tenant-config";
import { toastSuccess } from "@/lib/mutations";
import { cn } from "@/lib/utils";
import { PRICING_MODE_VALUES, TASK_TYPE_KIND_VALUES } from "@/lib/vocabulary";

import { useDeclareKinds } from "../api/queries";
import type { KindOfWork } from "../api/types";
import {
  formDefaults,
  kindFormSchema,
  revisionFormSchema,
  toDeclaration,
  type KindFormValues,
} from "../lib/declaration-form";
import {
  alreadyDeclared,
  altitudeLabel,
  declarationBody,
  declarationNotes,
  PRICING_MODE_EXPLANATIONS,
  pricingModeLabel,
} from "../lib/kinds";

/**
 * Declare a kind of work, or revise a standing one's policy.
 *
 * ⚠ THE POSTURE TRAP IS STATED HERE, BESIDE THE CONTROL (#423, spec §25
 * obligation 4). A workspace that meters without billing is told that the
 * regime it picks is inert today and becomes a start-gate refusal the day
 * billing is enabled; every workspace is told the regime cannot change
 * afterwards. Saying it when the field turns out to be read-only is the
 * failure this dialog exists to prevent.
 *
 * On a revision the key, the altitude and the regime are DISABLED: the first
 * two are the declaration's identity and the third is frozen (#187 §10). What
 * a revision may move is the ceiling and the two windows.
 *
 * There is no fraction-of-price ceiling here and no cap scoped to a grouping
 * field — both were revoked (#150 §5.2, §6.2) and #150 §6.4 addresses that
 * revocation at this surface. The ceiling is an absolute amount, and the
 * pinned set of controls in `declare-kind-dialog.test.tsx` holds it there.
 */
export function DeclareKindDialog({
  open,
  onOpenChange,
  standing,
  existing,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Every declaration the registry holds — the body re-declares all of them. */
  standing: readonly KindOfWork[];
  /** The kind being revised; absent when declaring a new one. */
  existing?: KindOfWork;
}) {
  const revising = existing !== undefined;
  const meteringOnly = useIsMeteringOnly();
  const currency = useTenantCurrency().toUpperCase();
  const declare = useDeclareKinds();
  const form = useForm<KindFormValues>({
    resolver: zodResolver(revising ? revisionFormSchema : kindFormSchema),
    defaultValues: formDefaults(existing),
  });

  React.useEffect(() => {
    if (open) {
      form.reset(formDefaults(existing));
      declare.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, existing]);

  const onSubmit = (values: KindFormValues) => {
    // ⚠ A NEW DECLARATION UNDER A STANDING IDENTITY IS REFUSED HERE, because
    // the route would not refuse it: an idempotent PUT with the same regime
    // ACCEPTS it, and the blank form's ceiling, windows and grouping fields
    // would silently replace the standing kind's. Revising is its own act,
    // from the kind's page, with the identity and the regime held fixed.
    if (!revising && alreadyDeclared(standing, { kind: values.kind, key: values.key })) {
      form.setError("key", {
        message:
          "A kind of work with this key is already declared at this altitude. Open it to " +
          "revise its ceiling and windows, or pick another key.",
      });
      return;
    }
    const declaration = toDeclaration(values, existing);
    declare.mutate(declarationBody(standing, declaration), {
      onSuccess: () => {
        toastSuccess(
          revising ? "Kind of work revised" : "Kind of work declared",
          revising
            ? `${declaration.key} keeps how it is sold; its ceiling and windows are updated.`
            : `${declaration.key} is declared as ${pricingModeLabel(declaration.pricing_mode).toLowerCase()}.`,
        );
        onOpenChange(false);
      },
    });
  };

  const errorMessage = declare.isError
    ? declare.error instanceof ApiProblem && declare.error.code === "pricing_mode_frozen"
      ? declare.error.message
      : problemMessage(declare.error)
    : null;

  const notes = declarationNotes({ meteringOnly });

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{revising ? "Revise a kind of work" : "Declare a kind of work"}</DialogTitle>
          <DialogDescription>
            {revising
              ? "The ceiling and the windows can move. What the kind is, and how it is sold, cannot."
              : "A kind of work is the unit your business sells. Its price lives in the pricing book; what you declare here is how it is sold and what it may spend."}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={(event) => void form.handleSubmit(onSubmit)(event)} className="space-y-4">
          <FormField
            label="Key"
            error={form.formState.errors.key?.message}
            hint={
              revising
                ? "The key is the declaration's identity and cannot change."
                : "The name your integration starts work under, e.g. video-render. Can't be changed later."
            }
          >
            {(id) => (
              <Input
                id={id}
                className="font-mono"
                placeholder="video-render"
                disabled={revising}
                {...form.register("key")}
              />
            )}
          </FormField>

          <fieldset className="space-y-1.5" disabled={revising}>
            <legend className="text-[13px] font-medium text-text-primary">Altitude</legend>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {TASK_TYPE_KIND_VALUES.map((value) => (
                <RadioOption
                  key={value}
                  title={altitudeLabel(value)}
                  description={
                    value === "task"
                      ? "A whole unit of work — the thing a customer is charged for."
                      : "Contained work, inside a whole unit. Never priced on its own."
                  }
                  disabled={revising}
                  input={<input type="radio" value={value} {...form.register("kind")} />}
                />
              ))}
            </div>
            {revising && (
              <p className="text-xs text-muted-foreground">
                One word may name a kind of work at either altitude; they are two declarations.
              </p>
            )}
          </fieldset>

          <fieldset className="space-y-1.5" disabled={revising}>
            <legend className="text-[13px] font-medium text-text-primary">How it is sold</legend>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {PRICING_MODE_VALUES.map((value) => (
                <RadioOption
                  key={value}
                  title={pricingModeLabel(value)}
                  description={PRICING_MODE_EXPLANATIONS[value]}
                  disabled={revising}
                  input={<input type="radio" value={value} {...form.register("pricing_mode")} />}
                />
              ))}
            </div>
            {notes.map((note) => (
              <p key={note} className="text-xs text-muted-foreground">
                {note}
              </p>
            ))}
          </fieldset>

          <FormField
            label={`Ceiling (${currency})`}
            error={form.formState.errors.ceiling?.message}
            hint="The most one run may spend on supplier cost before UBB stops it, as an amount. Leave it empty to use the workspace default."
          >
            {(id) => (
              <Input
                id={id}
                inputMode="decimal"
                placeholder="3.00"
                {...form.register("ceiling")}
              />
            )}
          </FormField>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <FormField
              label="Silence window (seconds)"
              error={form.formState.errors.silence_window_seconds?.message}
              hint="How long a run may go without reporting before it expires. Empty uses the workspace default."
            >
              {(id) => (
                <Input
                  id={id}
                  inputMode="numeric"
                  placeholder="600"
                  {...form.register("silence_window_seconds")}
                />
              )}
            </FormField>
            <FormField
              label="Absolute deadline (seconds)"
              error={form.formState.errors.absolute_deadline_seconds?.message}
              hint="The longest a run may live, reporting or not. Empty means no deadline."
            >
              {(id) => (
                <Input
                  id={id}
                  inputMode="numeric"
                  placeholder="7200"
                  {...form.register("absolute_deadline_seconds")}
                />
              )}
            </FormField>
          </div>

          {errorMessage && <p className="text-xs text-destructive">{errorMessage}</p>}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={declare.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={declare.isPending}>
              {declare.isPending ? "Working…" : revising ? "Save changes" : "Declare"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

/** One choice in a radio group, with the words for it beside the control. */
function RadioOption({
  title,
  description,
  disabled,
  input,
}: {
  title: string;
  description: string;
  disabled?: boolean;
  input: React.ReactNode;
}) {
  return (
    <label
      className={cn(
        "flex cursor-pointer items-start gap-2.5 rounded-lg border border-border px-3 py-2.5 hover:bg-bg-subtle/50",
        disabled && "cursor-not-allowed opacity-60 hover:bg-transparent",
      )}
    >
      <span className="mt-0.5">{input}</span>
      <span>
        <span className="block text-[13px] font-medium text-text-primary">{title}</span>
        <span className="mt-0.5 block text-xs text-text-secondary">{description}</span>
      </span>
    </label>
  );
}
