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
import { isCostBook, type AnyBook, type BookChangeIn, type BookRateChangeIn } from "../api/types";
import { agreedPriceChange } from "../lib/agreed-prices";
import { toMicros } from "../lib/pricing-math";
import {
  AGREED_PRICE_CHANGE_KINDS,
  CHANGE_KINDS,
  pinnableGroupingFields,
  selectorTitle,
  type ChangeKind,
} from "../lib/rules";
import {
  agreedPriceFormSchema,
  blankAgreedPrice,
  blankRule,
  resolveUnitQuantity,
  ruleFormSchema,
  statedGroupingFields,
  type AgreedPriceFormValues,
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

/** The same three acts, said of an agreed price (#553). */
const AGREED_PRICE_KINDS = Object.entries(AGREED_PRICE_CHANGE_KINDS).map(([value, words]) => ({
  value: value as ChangeKind,
  ...words,
}));

/** Which kind of line a change is about — the change body's `line` (#553). */
type Line = BookChangeIn["line"];

/**
 * Declare a change to a book — one draft, however many changes it carries.
 *
 * ⚠ **CHANGES ARE STAGED AND THE DRAFT IS DECLARED ONCE**, which is the shape
 * of the record rather than a convenience. A tenant agreeing a repricing does
 * not agree it one rule at a time; a dialog that declared a draft per rule
 * would record one decision as several, and then the diff a tenant reads before
 * committing would never be the decision they actually made.
 *
 * ⚠ **A PRICING BOOK HOLDS TWO KINDS OF LINE, AND ONE DRAFT MAY CARRY BOTH
 * (#553).** A rate prices a measured quantity; an agreed price prices one
 * delivered run of a kind of work. The tenant picks which a change is about,
 * and the draft stages either — one price list changes in one act. A cost
 * book holds rates only: a supplier's cost is never a customer's agreed price.
 *
 * ⚠ **NOTHING IS WRITTEN BY THIS DIALOG.** Declaring produces a draft with its
 * diff, and publishing it is a separate act on the panel behind.
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
  const holdsAgreedPrices = !isCostBook(book);
  const [staged, setStaged] = React.useState<BookChangeIn[]>([]);
  const [line, setLine] = React.useState<Line>("rate");
  const [kind, setKind] = React.useState<ChangeKind>("add");
  const [effectiveLocal, setEffectiveLocal] = React.useState("");

  const form = useForm<RuleFormValues>({
    resolver: zodResolver(ruleFormSchema),
    defaultValues: blankRule(),
  });
  const agreedForm = useForm<AgreedPriceFormValues>({
    resolver: zodResolver(agreedPriceFormSchema),
    defaultValues: blankAgreedPrice(),
  });

  React.useEffect(() => {
    if (open) {
      setStaged([]);
      setLine("rate");
      setKind("add");
      setEffectiveLocal("");
      form.reset(blankRule());
      agreedForm.reset(blankAgreedPrice());
      declare.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const declared = pinnableGroupingFields(groupingFields.data ?? []);
  const kindWords = line === "agreed_price" ? AGREED_PRICE_KINDS : KINDS;

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
    const change: BookRateChangeIn =
      kind === "retire"
        ? { line: "rate", kind, ...identity }
        : {
            line: "rate",
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

  const stageAgreedPrice = (values: AgreedPriceFormValues) => {
    // An add or a reprice states what one delivered run sells for; the form
    // admits an empty amount only because a retirement states none.
    if (kind !== "retire" && values.amount === "") {
      agreedForm.setError("amount", { message: "Required" });
      return;
    }
    setStaged((current) => [...current, agreedPriceChange(kind, values)]);
    agreedForm.reset(blankAgreedPrice());
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

  const kindChoice = (
    <fieldset className="space-y-1.5">
      <legend className="text-[13px] font-medium text-text-primary">
        What kind of change
      </legend>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
        {kindWords.map((entry) => (
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
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>Change this book</DialogTitle>
          <DialogDescription>
            Assemble the changes you want, then declare them as one draft. A
            draft writes nothing — you read its diff and publish it, or discard
            it and the book is exactly as it was.
          </DialogDescription>
        </DialogHeader>

        {staged.length > 0 && (
          <div className="space-y-2 rounded-lg border border-border p-3">
            <p className="text-[13px] font-medium text-text-primary">
              In this draft
            </p>
            <ul className="space-y-1.5">
              {staged.map((change, index) => {
                const subject =
                  change.line === "agreed_price" ? change.task_type : change.measurement_key;
                const words = change.line === "agreed_price" ? AGREED_PRICE_KINDS : KINDS;
                return (
                  <li
                    key={`${change.line}-${subject}-${index}`}
                    className="flex items-center justify-between gap-2"
                  >
                    <span className="flex min-w-0 items-center gap-2">
                      <Badge variant="outline" className="text-[10px]">
                        {words.find((entry) => entry.value === change.kind)?.offer ??
                          change.kind}
                      </Badge>
                      <span className="truncate font-mono text-[12px]">{subject}</span>
                    </span>
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      aria-label={`Remove ${subject} from this draft`}
                      onClick={() =>
                        setStaged((current) =>
                          current.filter((_, position) => position !== index),
                        )
                      }
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </li>
                );
              })}
            </ul>
          </div>
        )}

        {holdsAgreedPrices && (
          <fieldset className="space-y-1.5">
            <legend className="text-[13px] font-medium text-text-primary">
              What it prices
            </legend>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              {LINES.map((entry) => (
                <label
                  key={entry.value}
                  className="flex cursor-pointer gap-2 rounded-lg border border-border px-3 py-2 hover:bg-bg-subtle/50"
                >
                  <input
                    type="radio"
                    name="change-line"
                    className="mt-1"
                    value={entry.value}
                    checked={line === entry.value}
                    onChange={() => setLine(entry.value)}
                  />
                  <span className="min-w-0">
                    <span className="block text-[13px] font-medium text-text-primary">
                      {entry.title}
                    </span>
                    <span className="mt-0.5 block text-xs text-text-secondary">
                      {entry.hint}
                    </span>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>
        )}

        {line === "agreed_price" ? (
          <form
            onSubmit={(event) => void agreedForm.handleSubmit(stageAgreedPrice)(event)}
            className="space-y-4"
          >
            {kindChoice}
            <AgreedPriceFields form={agreedForm} retiring={kind === "retire"} currency={currency} />
            <Button type="submit" variant="outline" size="sm">
              Add to this draft
            </Button>
          </form>
        ) : (
          <form
            onSubmit={(event) => void form.handleSubmit(stage)(event)}
            className="space-y-4"
          >
            {kindChoice}
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
        )}

        <div className="border-t border-border pt-3">
          <EffectiveInstant
            label="Date this change ahead"
            hint="Publishing writes the change straight away and it takes effect at the instant you set — nothing has to run on the day. Within 366 days."
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

/** The two kinds of line a Pricing Book holds, in the words a tenant reads. */
const LINES: readonly { value: Line; title: string; hint: string }[] = [
  {
    value: "rate",
    title: "A rate",
    hint: "So much per unit of a measured quantity, per event.",
  },
  {
    value: "agreed_price",
    title: "An agreed price",
    hint: "One price per delivered run of a kind of work sold at one agreed price.",
  },
];

/**
 * An agreed price states a kind of work and what one delivered run of it sells
 * for — and a retirement states the kind alone, because it opens no line.
 *
 * The kind of work is any top-level kind you have declared and not retired,
 * whatever its current pricing mode, so the price can be declared before the
 * kind is switched to fixed pricing; the API refuses one declared only as
 * contained work, and the refusal reaches this dialog as its error.
 */
function AgreedPriceFields({
  form,
  retiring,
  currency,
}: {
  form: ReturnType<typeof useForm<AgreedPriceFormValues>>;
  retiring: boolean;
  currency: string;
}) {
  return (
    <div className="space-y-3">
      <FormField
        label="Kind of work"
        error={form.formState.errors.task_type?.message}
        hint="The key of a kind of work you declared on Tasks."
      >
        {(id) => <Input id={id} className="font-mono" {...form.register("task_type")} />}
      </FormField>
      {retiring ? (
        <Label className="text-xs text-muted-foreground">
          Retiring keeps the line's history and stops this book holding a price
          for that kind of work. A run already started keeps the price it pinned.
        </Label>
      ) : (
        <FormField
          label={`Agreed price per delivered run (${currency.toUpperCase()})`}
          error={form.formState.errors.amount?.message}
          hint="Zero is a price: the run is delivered for nothing, on purpose."
        >
          {(id) => <Input id={id} inputMode="decimal" {...form.register("amount")} />}
        </FormField>
      )}
    </div>
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
        <FormField label={selectorTitle("provider")}>
          {(id) => <Input id={id} className="font-mono" {...form.register("provider")} />}
        </FormField>
        <FormField label={selectorTitle("event_type")}>
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
