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
import { useCreateBook } from "../api/queries";
import type { Book } from "../api/types";
import { bookFormSchema, type BookFormValues } from "../lib/schemas";

const DEFAULTS: BookFormValues = {
  card_type: "cost",
  key: "",
  name: "",
  provider_key: "",
  is_default: false,
};

/** Create a rate-card book (cost or price). Price books need the Billing product. */
export function CreateBookDialog({
  open,
  onOpenChange,
  onCreated,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated?: (book: Book) => void;
}) {
  const hasBilling = useHasProduct("billing");
  const create = useCreateBook();
  const form = useForm<BookFormValues>({
    resolver: zodResolver(bookFormSchema),
    defaultValues: DEFAULTS,
  });
  const cardType = form.watch("card_type");

  React.useEffect(() => {
    if (open) {
      form.reset(DEFAULTS);
      create.reset();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  const onSubmit = (values: BookFormValues) => {
    create.mutate(
      {
        card_type: values.card_type,
        key: values.key,
        name: values.name,
        provider_key: values.provider_key,
        is_default: values.is_default,
      },
      {
        onSuccess: (book) => {
          toastSuccess("Book created", `${book.name || book.key} is ready for rates.`);
          onOpenChange(false);
          onCreated?.(book);
        },
      },
    );
  };

  const errorMessage = create.isError
    ? create.error instanceof ApiProblem && create.error.code === "conflict"
      ? `A ${cardType} book with this key already exists — pick a different key.`
      : problemMessage(create.error)
    : null;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New rate-card book</DialogTitle>
          <DialogDescription>
            A book holds the rates for one provider and one currency. Rates you
            add to it are live immediately.
          </DialogDescription>
        </DialogHeader>
        <form
          onSubmit={(event) => void form.handleSubmit(onSubmit)(event)}
          className="space-y-4"
        >
          <div className="space-y-1.5">
            <Label>Book type</Label>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <CardTypeOption
                selected={cardType === "cost"}
                title="Cost card"
                description="What providers charge you (your COGS)."
                onSelect={() => form.setValue("card_type", "cost")}
              />
              <CardTypeOption
                selected={cardType === "price"}
                title="Price card"
                description="What you bill your customers."
                disabled={!hasBilling}
                onSelect={() => form.setValue("card_type", "price")}
              />
            </div>
            {!hasBilling && (
              <p className="text-xs text-muted-foreground">
                Price books need the Billing product, which isn't enabled for
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
          <FormField
            label="Provider (optional)"
            error={form.formState.errors.provider_key?.message}
            hint="The provider whose events this book prices, e.g. openai."
          >
            {(id) => (
              <Input id={id} className="font-mono" placeholder="openai" {...form.register("provider_key")} />
            )}
          </FormField>
          <div className="flex items-start gap-2.5">
            <Switch
              checked={form.watch("is_default")}
              onCheckedChange={(checked) => form.setValue("is_default", checked)}
              aria-label="Default book for its provider"
            />
            <div>
              <p className="text-[13px] font-medium text-text-primary">
                Default book for this provider
              </p>
              <p className="text-xs text-muted-foreground">
                Used automatically for the provider's events when no book is
                assigned to the customer.
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
              {create.isPending ? "Working…" : "Create book"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

function CardTypeOption({
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
