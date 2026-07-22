import { useState, type KeyboardEvent } from "react";
import { X } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";

/** Event types the backend is known to emit — offered as quick-add suggestions.
 *  The API accepts arbitrary strings, so this is guidance, not a closed set. */
const SUGGESTED = [
  "usage.recorded",
  "stop.fired",
  "balance.low",
  "grant.expiring",
  "invoice.paid",
  "invoice.finalized",
  "topup.completed",
  "subscription.updated",
];

/**
 * Tag-style editor for the webhook `event_types` array. Type + Enter (or comma)
 * to add; click a suggestion to add it; × to remove. The event-type vocabulary
 * is open (not enumerated in the API spec), so free entry is allowed.
 */
export function EventTypesInput({
  value,
  onChange,
  invalid,
}: {
  value: string[];
  onChange: (next: string[]) => void;
  invalid?: boolean;
}) {
  const [draft, setDraft] = useState("");

  const add = (raw: string) => {
    const v = raw.trim();
    if (!v || value.includes(v)) return;
    onChange([...value, v]);
  };
  const remove = (v: string) => onChange(value.filter((x) => x !== v));

  const onKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      add(draft);
      setDraft("");
    } else if (e.key === "Backspace" && !draft && value.length) {
      const last = value[value.length - 1];
      if (last) remove(last);
    }
  };

  const available = SUGGESTED.filter((s) => !value.includes(s));

  return (
    <div className="flex flex-col gap-2">
      <div
        className={cn(
          "flex min-h-8 flex-wrap items-center gap-1.5 rounded-lg border border-input px-2 py-1.5",
          invalid && "border-destructive",
        )}
      >
        {value.map((v) => (
          <Badge key={v} variant="secondary" className="gap-1 rounded-md font-normal">
            {v}
            <button
              type="button"
              onClick={() => remove(v)}
              aria-label={`Remove ${v}`}
              className="text-muted-foreground hover:text-foreground"
            >
              <X className="size-3" />
            </button>
          </Badge>
        ))}
        <input
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={onKeyDown}
          onBlur={() => {
            if (draft.trim()) {
              add(draft);
              setDraft("");
            }
          }}
          placeholder={value.length ? "Add another…" : "e.g. usage.recorded"}
          className="min-w-[8rem] flex-1 bg-transparent text-sm outline-none placeholder:text-muted-foreground"
        />
      </div>
      {available.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {available.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => add(s)}
              className="rounded-md border border-dashed border-border px-1.5 py-0.5 text-xs text-muted-foreground transition-colors hover:border-foreground hover:text-foreground"
            >
              + {s}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
