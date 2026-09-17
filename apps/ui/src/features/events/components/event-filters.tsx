// Ledger filters, all URL-backed: past-limit toggle, stop scope, episode
// number, and a metadata key/value pair. Text inputs commit on blur or Enter so
// typing doesn't refetch per keystroke.
//
// ⚠ **THE PAIR IS NAMED FOR THE BAG IT READS, IN THE COPY AS WELL AS IN THE
// STATE (#507).** It carried the analytics grouping word on every surface from
// the URL to the label, and a tenant reading "Tag" here had no way to connect
// it to the metadata their own events carry — which is the bag this actually
// filters, named that way on the wire since #504 and on the event's own detail
// page long before. A key is whatever the TENANT wrote, so the inputs stay free
// text: there is no catalogue to offer and nothing here to word for them.

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { stopScopeLabel } from "@/lib/labels";

import { STOP_SCOPES, type EventsSearch } from "../lib/search";

const ANY_SCOPE = "any";

function CommitInput({
  id,
  value,
  onCommit,
  placeholder,
  className,
  inputMode,
}: {
  id: string;
  value: string;
  onCommit: (next: string) => void;
  placeholder?: string;
  className?: string;
  inputMode?: "numeric";
}) {
  const [draft, setDraft] = useState(value);
  // Re-sync when the committed value changes from outside (URL navigation) —
  // render-time adjustment instead of an effect, per React guidance.
  const [lastValue, setLastValue] = useState(value);
  if (value !== lastValue) {
    setLastValue(value);
    setDraft(value);
  }
  const commit = () => {
    const trimmed = draft.trim();
    if (trimmed !== value) onCommit(trimmed);
  };
  return (
    <Input
      id={id}
      value={draft}
      inputMode={inputMode}
      placeholder={placeholder}
      className={className}
      onChange={(event) => setDraft(event.target.value)}
      onBlur={commit}
      onKeyDown={(event) => {
        if (event.key === "Enter") commit();
      }}
    />
  );
}

export interface FilterPatch {
  past_limit?: boolean;
  stop_scope?: EventsSearch["stop_scope"];
  episode_seq?: number;
  metadata_key?: string;
  metadata_value?: string;
}

export function EventFilters({
  search,
  onChange,
}: {
  search: EventsSearch;
  onChange: (patch: FilterPatch) => void;
}) {
  const anyActive =
    search.past_limit !== undefined ||
    search.stop_scope !== undefined ||
    search.episode_seq !== undefined ||
    search.metadata_key !== undefined ||
    search.metadata_value !== undefined;

  return (
    <div className="flex flex-wrap items-end gap-4">
      <div className="flex h-8 items-center gap-2">
        <Switch
          id="filter-past-limit"
          checked={search.past_limit === true}
          onCheckedChange={(checked) =>
            onChange({ past_limit: checked ? true : undefined })
          }
        />
        <Label htmlFor="filter-past-limit" className="text-[12px]">
          Past-limit only
        </Label>
      </div>

      <div className="space-y-1">
        <Label className="text-[11px] text-text-muted">Stop scope</Label>
        <Select
          value={search.stop_scope ?? ANY_SCOPE}
          onValueChange={(value) =>
            onChange({
              stop_scope:
                typeof value === "string" && value !== ANY_SCOPE
                  ? STOP_SCOPES.find((scope) => scope === value)
                  : undefined,
            })
          }
        >
          <SelectTrigger
            className="h-8 w-[130px] text-[12px]"
            aria-label="Stop scope"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ANY_SCOPE}>Any scope</SelectItem>
            {STOP_SCOPES.map((scope) => (
              <SelectItem key={scope} value={scope}>
                {stopScopeLabel(scope)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="space-y-1">
        <Label htmlFor="filter-episode" className="text-[11px] text-text-muted">
          Stop episode
        </Label>
        <CommitInput
          id="filter-episode"
          value={search.episode_seq !== undefined ? String(search.episode_seq) : ""}
          inputMode="numeric"
          placeholder="e.g. 3"
          className="h-8 w-[90px] text-[12px]"
          onCommit={(next) => {
            const parsed = Number.parseInt(next, 10);
            onChange({
              episode_seq:
                Number.isInteger(parsed) && parsed >= 0 ? parsed : undefined,
            });
          }}
        />
      </div>

      <div className="space-y-1">
        <Label
          htmlFor="filter-metadata-key"
          className="text-[11px] text-text-muted"
        >
          Metadata
        </Label>
        <div className="flex items-center gap-1">
          <CommitInput
            id="filter-metadata-key"
            value={search.metadata_key ?? ""}
            placeholder="key"
            className="h-8 w-[110px] text-[12px]"
            onCommit={(next) =>
              onChange({ metadata_key: next === "" ? undefined : next })
            }
          />
          <span className="text-[12px] text-text-muted">=</span>
          <CommitInput
            id="filter-metadata-value"
            value={search.metadata_value ?? ""}
            placeholder="value"
            className="h-8 w-[110px] text-[12px]"
            onCommit={(next) =>
              onChange({ metadata_value: next === "" ? undefined : next })
            }
          />
        </div>
      </div>

      {anyActive && (
        <Button
          variant="ghost"
          size="sm"
          onClick={() =>
            onChange({
              past_limit: undefined,
              stop_scope: undefined,
              episode_seq: undefined,
              metadata_key: undefined,
              metadata_value: undefined,
            })
          }
        >
          Clear filters
        </Button>
      )}

      {(search.metadata_key === undefined) !==
        (search.metadata_value === undefined) && (
        <p className="w-full text-[11px] text-text-muted">
          Both a metadata key and a value are needed for this filter to apply.
        </p>
      )}
    </div>
  );
}
