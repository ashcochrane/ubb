import * as React from "react";

import { Checkbox } from "@/components/ui/checkbox";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";

import { groupedEventTypes } from "../lib/event-groups";

const GROUPS = groupedEventTypes();

/**
 * Event subscription picker: either "All events (*)" — every current AND
 * future event type — or an explicit selection from the grouped catalog
 * (at least one required; validated by the form schema).
 */
export function EventTypePicker({
  allEvents,
  onAllEventsChange,
  selected,
  onSelectedChange,
  error,
}: {
  allEvents: boolean;
  onAllEventsChange: (allEvents: boolean) => void;
  selected: string[];
  onSelectedChange: (next: string[]) => void;
  error?: string;
}) {
  const allEventsId = React.useId();
  const idPrefix = React.useId();
  const selectedSet = React.useMemo(() => new Set(selected), [selected]);

  const toggle = (eventType: string, checked: boolean) => {
    onSelectedChange(
      checked
        ? [...selected, eventType]
        : selected.filter((value) => value !== eventType),
    );
  };

  return (
    <div className="flex flex-col gap-1.5">
      <Label>Subscribed events</Label>
      <div className="flex items-center justify-between gap-3 rounded-lg border border-border px-3 py-2">
        <div className="min-w-0">
          <Label htmlFor={allEventsId}>All events (*)</Label>
          <p className="mt-0.5 text-xs text-muted-foreground">
            Every current and future event type — new types are added over time.
          </p>
        </div>
        <Switch
          id={allEventsId}
          checked={allEvents}
          onCheckedChange={(checked) => onAllEventsChange(checked)}
        />
      </div>
      {!allEvents && (
        <div className="max-h-56 space-y-3 overflow-y-auto rounded-lg border border-border p-3">
          {GROUPS.map((group) => (
            <fieldset key={group.key}>
              <legend className="mb-1.5 text-xs font-medium text-muted-foreground">
                {group.label}
              </legend>
              <div className="grid gap-1.5 sm:grid-cols-2">
                {group.options.map((option) => {
                  const id = `${idPrefix}-${option.value}`;
                  return (
                    <div key={option.value} className="flex items-center gap-2">
                      <Checkbox
                        id={id}
                        checked={selectedSet.has(option.value)}
                        onCheckedChange={(checked) => toggle(option.value, checked === true)}
                      />
                      <Label htmlFor={id} className="cursor-pointer font-normal">
                        {option.label}
                      </Label>
                    </div>
                  );
                })}
              </div>
            </fieldset>
          ))}
        </div>
      )}
      {error && <p className="text-xs text-destructive">{error}</p>}
    </div>
  );
}
