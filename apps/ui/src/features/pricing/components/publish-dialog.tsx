import { useState, type ReactNode } from "react";
import { useForm, useFieldArray } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { Plus, Trash2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogClose,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { FormField } from "@/components/shared/form-field";
import { usePublishBook } from "../api/queries";
import {
  publishSchema,
  PRICING_MODELS,
  type PublishValues,
} from "../lib/schema";

const SELECT_CLASS =
  "h-8 w-full rounded-lg border border-input bg-transparent px-2.5 text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50";

const EMPTY_CHANGE = {
  metric_name: "",
  provider: "",
  event_type: "",
  pricing_model: "per_unit",
  rate_per_unit: 0,
};

/**
 * Stage one or more rate changes and publish them as a new rate-card version.
 * Publishing mints a new version and never rewrites existing history — past
 * usage stays priced at the version that was live when it was recorded.
 */
export function PublishDialog({
  bookId,
  trigger,
}: {
  bookId: string;
  trigger: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const publish = usePublishBook(bookId);

  const form = useForm<PublishValues>({
    resolver: zodResolver(publishSchema),
    defaultValues: { changes: [{ ...EMPTY_CHANGE }] },
  });
  const { fields, append, remove } = useFieldArray({
    control: form.control,
    name: "changes",
  });
  const { errors } = form.formState;

  const onSubmit = form.handleSubmit(async (values) => {
    await publish.mutateAsync({
      changes: values.changes.map((c) => ({
        metric_name: c.metric_name,
        provider: c.provider,
        event_type: c.event_type,
        pricing_model: c.pricing_model,
        rate_per_unit_micros: Math.round(c.rate_per_unit * 1_000_000),
      })),
    });
    setOpen(false);
    form.reset({ changes: [{ ...EMPTY_CHANGE }] });
  });

  return (
    <Dialog
      open={open}
      onOpenChange={(v) => {
        setOpen(v);
        if (!v) form.reset({ changes: [{ ...EMPTY_CHANGE }] });
      }}
    >
      <DialogTrigger render={trigger as React.ReactElement} />
      <DialogContent className="sm:max-w-lg">
        <form onSubmit={onSubmit}>
          <DialogHeader>
            <DialogTitle>Publish changes</DialogTitle>
            <DialogDescription>
              Staged changes are published together as a new version. Publishing
              never rewrites history — usage already recorded keeps its original
              price.
            </DialogDescription>
          </DialogHeader>

          <div className="mt-4 flex flex-col gap-4">
            {fields.map((field, i) => (
              <div
                key={field.id}
                className="flex flex-col gap-3 rounded-lg border border-border p-3"
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium text-muted-foreground">
                    Change {i + 1}
                  </span>
                  {fields.length > 1 && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon-sm"
                      onClick={() => remove(i)}
                      aria-label="Remove change"
                    >
                      <Trash2 />
                    </Button>
                  )}
                </div>

                <FormField
                  label="Metric name"
                  error={errors.changes?.[i]?.metric_name?.message}
                >
                  {(id) => (
                    <Input
                      id={id}
                      placeholder="input_tokens"
                      {...form.register(`changes.${i}.metric_name` as const)}
                    />
                  )}
                </FormField>

                <div className="grid grid-cols-2 gap-3">
                  <FormField
                    label="Provider"
                    error={errors.changes?.[i]?.provider?.message}
                  >
                    {(id) => (
                      <Input
                        id={id}
                        placeholder="openai"
                        {...form.register(`changes.${i}.provider` as const)}
                      />
                    )}
                  </FormField>
                  <FormField
                    label="Event type"
                    error={errors.changes?.[i]?.event_type?.message}
                  >
                    {(id) => (
                      <Input
                        id={id}
                        placeholder="completion"
                        {...form.register(`changes.${i}.event_type` as const)}
                      />
                    )}
                  </FormField>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <FormField
                    label="Pricing model"
                    error={errors.changes?.[i]?.pricing_model?.message}
                  >
                    {(id) => (
                      <select
                        id={id}
                        className={SELECT_CLASS}
                        {...form.register(`changes.${i}.pricing_model` as const)}
                      >
                        {PRICING_MODELS.map((m) => (
                          <option key={m} value={m}>
                            {m}
                          </option>
                        ))}
                      </select>
                    )}
                  </FormField>
                  <FormField
                    label="New rate per unit (USD)"
                    error={errors.changes?.[i]?.rate_per_unit?.message}
                  >
                    {(id) => (
                      <Input
                        id={id}
                        type="number"
                        min={0}
                        step="any"
                        {...form.register(`changes.${i}.rate_per_unit` as const, {
                          valueAsNumber: true,
                        })}
                      />
                    )}
                  </FormField>
                </div>
              </div>
            ))}

            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => append({ ...EMPTY_CHANGE })}
            >
              <Plus />
              Add another change
            </Button>
          </div>

          <DialogFooter className="mt-2">
            <DialogClose render={<Button variant="outline" type="button" disabled={publish.isPending} />}>
              Cancel
            </DialogClose>
            <Button type="submit" disabled={publish.isPending}>
              {publish.isPending ? "Publishing…" : "Publish new version"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
