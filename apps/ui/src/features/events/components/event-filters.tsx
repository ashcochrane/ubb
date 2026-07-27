// Ledger filters, all URL-backed: past-limit toggle, stop scope, episode
// number, and a tag key/value pair. Text inputs commit on blur or Enter so
// typing doesn't refetch per keystroke.

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
  tag_key?: string;
  tag_value?: string;
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
    search.tag_key !== undefined ||
    search.tag_value !== undefined;

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
        <Label htmlFor="filter-tag-key" className="text-[11px] text-text-muted">
          Tag
        </Label>
        <div className="flex items-center gap-1">
          <CommitInput
            id="filter-tag-key"
            value={search.tag_key ?? ""}
            placeholder="key"
            className="h-8 w-[110px] text-[12px]"
            onCommit={(next) =>
              onChange({ tag_key: next === "" ? undefined : next })
            }
          />
          <span className="text-[12px] text-text-muted">=</span>
          <CommitInput
            id="filter-tag-value"
            value={search.tag_value ?? ""}
            placeholder="value"
            className="h-8 w-[110px] text-[12px]"
            onCommit={(next) =>
              onChange({ tag_value: next === "" ? undefined : next })
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
              tag_key: undefined,
              tag_value: undefined,
            })
          }
        >
          Clear filters
        </Button>
      )}

      {(search.tag_key === undefined) !== (search.tag_value === undefined) && (
        <p className="w-full text-[11px] text-text-muted">
          Both a tag key and a value are needed for the tag filter to apply.
        </p>
      )}
    </div>
  );
}
