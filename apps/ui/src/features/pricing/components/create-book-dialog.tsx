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
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useHasProduct } from "@/hooks/use-tenant-config";
import { cn } from "@/lib/utils";
import { toastSuccess } from "@/lib/mutations";
import { useDeclareCostBook, useDeclarePricingBook } from "../api/queries";
import type { AnyBook } from "../api/types";
import { bookFormSchema, type BookFormValues } from "../lib/schemas";

const DEFAULTS: BookFormValues = {
  key: "",
  name: "",
  provider_key: "",
  is_default: false,
};

type Kind = "cost" | "pricing";

/**
 * Declare a book — a cost book or a Pricing Book.
 *
 * ⚠ **THE CHOICE IS WHICH ROUTE TO CALL, NOT A FIELD ON ONE BODY (#368).**
 * The two entities take different bodies because they have different columns:
 * a cost book names the supplier it records and the currency that supplier
 * bills in, a Pricing Book names neither. So the kind lives in this dialog's
 * own state and picks a mutation, and the supplier field is shown only for the
 * half that has one. A single body carrying a kind word is what the split
 * deleted.
 *
 * A Pricing Book needs the Billing product; a cost book is always available.
 */
export function CreateBookDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated?: (book: AnyBook) => void;
}) {
  const hasBilling = useHasProduct("billing");
  const [kind, setKind] = React.useState<Kind>("cost");
  const declareCost = useDeclareCostBook();
  const declarePricing = useDeclarePricingBook();
  const create = kind === "cost" ? declareCost : declarePricing;
  const form = useForm<BookFormValues>({
    resolver: zodResolver(bookFormSchema),
    defaultValues: DEFAULTS,
  });

  React.useEffect(() => {
    if (open) {
      form.reset(DEFAULTS);
      setKind("cost");
      declareCost.reset();
      declarePricing.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const onSubmit = (values: BookFormValues) => {
    const onSuccess = (book: AnyBook) => {
      toastSuccess("Book declared", `${book.name || book.key} is ready for rules.`);
      onOpenChange(false);
      onCreated?.(book);
    };
    // Each half is handed the fields ITS OWN body takes. The supplier is a
    // cost book's and the Pricing Book route publishes no such property, so
    // sending it would be a key django-ninja silently drops.
    if (kind === "cost") {
      declareCost.mutate(
        {
          key: values.key,
          name: values.name,
          provider_key: values.provider_key,
          is_default: values.is_default,
        },
        { onSuccess },
      );
    } else {
      declarePricing.mutate(
        { key: values.key, name: values.name, is_default: values.is_default },
        { onSuccess },
      );
    }
  };

  const errorMessage = create.isError
    ? create.error instanceof ApiProblem && create.error.code === "conflict"
      ? `A ${kind === "cost" ? "cost" : "pricing"} book with this key already ` +
        `exists — pick a different key.`
      : problemMessage(create.error)
    : null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Declare a book</DialogTitle>
          <DialogDescription>
            A book arrives empty and gains rules by a published change. A cost
            book records what one supplier charges you; a pricing book sets
            what your customers are billed.
          </DialogDescription>
        </DialogHeader>
        <form
          onSubmit={(event) => void form.handleSubmit(onSubmit)(event)}
          className="space-y-4"
        >
          <div className="space-y-1.5">
            <Label>Book type</Label>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <BookKindOption
                selected={kind === "cost"}
                title="Cost book"
                description="What one supplier charges you (your COGS)."
                onSelect={() => setKind("cost")}
              />
              <BookKindOption
                selected={kind === "pricing"}
                title="Pricing book"
                description="What you bill your customers."
                disabled={!hasBilling}
                onSelect={() => setKind("pricing")}
              />
            </div>
            {!hasBilling && (
              <p className="text-xs text-muted-foreground">
                Pricing books need the Billing product, which isn't enabled for
                this workspace. Cost books are always available.
              </p>
            )}
          </div>
          <FormField
            label="Key"
            error={form.formState.errors.key?.message}
            hint="Unique identifier for this book, e.g. openai-cogs. Can't be changed later."
          >
            {(id) => (
              <Input id={id} className="font-mono" placeholder="openai-cogs" {...form.register("key")} />
            )}
          </FormField>
          <FormField
            label="Name (optional)"
            error={form.formState.errors.name?.message}
          >
            {(id) => (
              <Input id={id} placeholder="OpenAI provider costs" {...form.register("name")} />
            )}
          </FormField>
          {kind === "cost" && (
            <FormField
              label="Supplier (optional)"
              error={form.formState.errors.provider_key?.message}
              hint="The supplier whose events this book costs, e.g. openai. Leave it empty for a book that applies whatever the supplier."
            >
              {(id) => (
                <Input id={id} className="font-mono" placeholder="openai" {...form.register("provider_key")} />
              )}
            </FormField>
          )}
          <div className="flex items-start gap-2.5">
            <Switch
              checked={form.watch("is_default")}
              onCheckedChange={(checked) => form.setValue("is_default", checked)}
              aria-label="Default book"
            />
            <div>
              <p className="text-[13px] font-medium text-text-primary">
                {kind === "cost"
                  ? "Default book for this supplier"
                  : "Default pricing book"}
              </p>
              <p className="text-xs text-muted-foreground">
                {kind === "cost"
                  ? "Used automatically for that supplier's events."
                  : "Used for any customer whose plan names no book of its own."}
              </p>
            </div>
          </div>
          {errorMessage && <p className="text-xs text-destructive">{errorMessage}</p>}
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
              disabled={create.isPending}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? "Working…" : "Declare book"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function BookKindOption({
  selected,
  title,
  description,
  disabled,
  onSelect,
}: {
  selected: boolean;
  title: string;
  description: string;
  disabled?: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      aria-pressed={selected}
      disabled={disabled}
      onClick={onSelect}
      className={cn(
        "rounded-lg border px-3 py-2.5 text-left transition-colors",
        selected
          ? "border-border-strong bg-bg-subtle"
          : "border-border hover:bg-bg-subtle/50",
        disabled && "cursor-not-allowed opacity-50 hover:bg-transparent",
      )}
    >
      <p className="text-[13px] font-medium text-text-primary">{title}</p>
      <p className="mt-0.5 text-xs text-text-secondary">{description}</p>
    </button>
  );
}
