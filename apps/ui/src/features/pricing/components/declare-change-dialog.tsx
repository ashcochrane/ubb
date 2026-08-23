import * as React from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useForm } from "react-hook-form";
import { Trash2 } from "lucide-react";

import { FormField } from "@/components/shared/form-field";
import { Badge } from "@/components/ui/badge";
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
import { Label } from "@/components/ui/label";
import { toastSuccess } from "@/lib/mutations";
import { useDeclareBookPublish, useGroupingFields } from "../api/queries";
import type { AnyBook, BookChangeIn } from "../api/types";
import { toMicros } from "../lib/pricing-math";
import { CHANGE_KINDS, pinnableGroupingFields, type ChangeKind } from "../lib/rules";
import {
  blankRule,
  resolveUnitQuantity,
  ruleFormSchema,
  statedGroupingFields,
  type RuleFormValues,
} from "../lib/schemas";
import { effectiveInstant, scheduleRefusal } from "../lib/schedule";
import { EffectiveInstant } from "./effective-instant";
import { RuleEditor } from "./rule-editor";

/** The three acts, in the order a tenant meets them. Wording is the lib's. */
const KINDS = Object.entries(CHANGE_KINDS).map(([value, words]) => ({
  value: value as ChangeKind,
  ...words,
}));

/**
 * Declare a change to a book — one draft, however many changes it carries.
 *
 * ⚠ **CHANGES ARE STAGED AND THE DRAFT IS DECLARED ONCE**, which is the shape
 * of the record rather than a convenience. A tenant agreeing a repricing does
 * not agree it one rule at a time; a dialog that declared a draft per rule
 * would record one decision as several, and then the diff a tenant reads before
 * committing would never be the decision they actually made. So the staging
 * list lives here, in the console, and the API sees one body.
 *
 * ⚠ **NOTHING IS WRITTEN BY THIS DIALOG.** Declaring produces a draft with its
 * diff, and publishing it is a separate act on the panel behind. That is the
 * whole point of the two-step: a tenant decides against the OUTCOME rather than
 * against their own request.
 */
export function DeclareChangeDialog({
  book,
  open,
  onOpenChange,
}: {
  book: AnyBook;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const declare = useDeclareBookPublish(book.id);
  const groupingFields = useGroupingFields();
  const currency = "currency" in book ? book.currency : "usd";
  const [staged, setStaged] = React.useState<BookChangeIn[]>([]);
  const [kind, setKind] = React.useState<ChangeKind>("add");
  const [effectiveLocal, setEffectiveLocal] = React.useState("");

  const form = useForm<RuleFormValues>({
    resolver: zodResolver(ruleFormSchema),
    defaultValues: blankRule(),
  });

  React.useEffect(() => {
    if (open) {
      setStaged([]);
      setKind("add");
      setEffectiveLocal("");
      form.reset(blankRule());
      declare.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const declared = pinnableGroupingFields(groupingFields.data ?? []);

  const stage = (values: RuleFormValues) => {
    const identity = {
      measurement_key: values.measurement_key,
      provider: values.provider,
      event_type: values.event_type,
      task_type: values.task_type,
      subtask_type: values.subtask_type,
      grouping_fields: statedGroupingFields(values.grouping_fields),
    };
    // ⚠ A RETIRE STATES NONE OF THE TERMS AT ALL — it opens no rule, so an
    // amount on it would be a number nobody will ever read. The contract makes
    // every term nullable for exactly this reason and the body follows it.
    const change: BookChangeIn =
      kind === "retire"
        ? { kind, ...identity }
        : {
            kind,
            ...identity,
            pricing_method: values.pricing_method,
            rate_structure: values.rate_structure,
            rate_per_unit_micros: toMicros(values.rate),
            unit_quantity: resolveUnitQuantity(values),
            fixed_micros: toMicros(values.fixed),
          };
    setStaged((current) => [...current, change]);
    form.reset(blankRule());
  };


  const submit = () => {
    declare.mutate(
      { changes: staged, effective_at: effectiveInstant(effectiveLocal) },
      {
        onSuccess: (publish) => {
          toastSuccess(
            "Change declared",
            `${staged.length} ${staged.length === 1 ? "change" : "changes"} in one draft. Read the diff, then publish it.`,
          );
          onOpenChange(false);
          void publish;
        },
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Change this book</DialogTitle>
          <DialogDescription>
            Assemble the changes you want, then declare them as one draft. A
            draft writes no rules — you read its diff and publish it, or discard
            it and the book is exactly as it was.
          </DialogDescription>
        </DialogHeader>

        {staged.length > 0 && (
          <div className="space-y-2 rounded-lg border border-border p-3">
            <p className="text-[13px] font-medium text-text-primary">
              In this draft
            </p>
            <ul className="space-y-1.5">
              {staged.map((change, index) => (
                <li
                  key={`${change.measurement_key}-${index}`}
                  className="flex items-center justify-between gap-2"
                >
                  <span className="flex min-w-0 items-center gap-2">
                    <Badge variant="outline" className="text-[10px]">
                      {KINDS.find((entry) => entry.value === change.kind)?.offer ??
                        change.kind}
                    </Badge>
                    <span className="truncate font-mono text-[12px]">
                      {change.measurement_key}
                    </span>
                  </span>
                  <Button
                    type="button"
                    size="sm"
                    variant="ghost"
                    aria-label={`Remove ${change.measurement_key} from this draft`}
                    onClick={() =>
                      setStaged((current) =>
                        current.filter((_, position) => position !== index),
                      )
                    }
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </li>
              ))}
            </ul>
          </div>
        )}

        <form
          onSubmit={(event) => void form.handleSubmit(stage)(event)}
          className="space-y-4"
        >
          <fieldset className="space-y-1.5">
            <legend className="text-[13px] font-medium text-text-primary">
              What kind of change
            </legend>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
              {KINDS.map((entry) => (
                <label
                  key={entry.value}
                  className="flex cursor-pointer gap-2 rounded-lg border border-border px-3 py-2 hover:bg-bg-subtle/50"
                >
                  <input
                    type="radio"
                    name="change-kind"
                    className="mt-1"
                    value={entry.value}
                    checked={kind === entry.value}
                    onChange={() => setKind(entry.value)}
                  />
                  <span className="min-w-0">
                    <span className="block text-[13px] font-medium text-text-primary">
                      {entry.offer}
                    </span>
                    <span className="mt-0.5 block text-xs text-text-secondary">
                      {entry.hint}
                    </span>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>

          {kind === "retire" ? (
            <RetireFields form={form} />
          ) : (
            <RuleEditor
              form={form}
              groupingFields={declared}
              currency={currency}
            />
          )}

          <Button type="submit" variant="outline" size="sm">
            Add to this draft
          </Button>
        </form>

        <div className="border-t border-border pt-3">
          <EffectiveInstant
            label="Date this change ahead"
            hint="Publishing writes the rules straight away and they take effect at the instant you set — nothing has to run on the day. Within 366 days."
            value={effectiveLocal}
            onChange={setEffectiveLocal}
          />
        </div>

        {declare.isError && (
          <p className="text-xs text-destructive">
            {scheduleRefusal(declare.error)}
          </p>
        )}

        <DialogFooter>
          <Button
            type="button"
            variant="outline"
            onClick={() => onOpenChange(false)}
            disabled={declare.isPending}
          >
            Cancel
          </Button>
          <Button
            type="button"
            onClick={submit}
            disabled={staged.length === 0 || declare.isPending}
          >
            {declare.isPending
              ? "Working…"
              : `Declare ${staged.length || ""} ${staged.length === 1 ? "change" : "changes"}`.trim()}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/**
 * A retire states which rule and nothing else.
 *
 * The terms are deliberately absent rather than disabled: a retire opens no
 * rule, so an amount beside it would be a number the record will never carry
 * and a tenant would reasonably expect to mean something.
 */
function RetireFields({ form }: { form: ReturnType<typeof useForm<RuleFormValues>> }) {
  return (
    <div className="space-y-3">
      <FormField
        label="Measurement"
        error={form.formState.errors.measurement_key?.message}
        hint="The rule to stop pricing, identified by the quantity it prices plus what it pins."
      >
        {(id) => (
          <Input id={id} className="font-mono" {...form.register("measurement_key")} />
        )}
      </FormField>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <FormField label="Provider">
          {(id) => <Input id={id} className="font-mono" {...form.register("provider")} />}
        </FormField>
        <FormField label="Event type">
          {(id) => (
            <Input id={id} className="font-mono" {...form.register("event_type")} />
          )}
        </FormField>
      </div>
      <Label className="text-xs text-muted-foreground">
        Retiring reopens nothing and revives nothing. Whatever the customer
        would otherwise have matched was there all along, out-ranked, and starts
        answering again.
      </Label>
    </div>
  );
}
