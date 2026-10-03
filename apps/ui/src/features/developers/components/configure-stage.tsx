// Configure: what an integration does, as far as it has to be said (#579).
//
// FOUR QUESTIONS, AND ONLY THE FOUR THE REQUEST PUBLISHES
// (`IntegrationBlueprintSelectionIn`): the target, the kind of work, the Event
// Types, and — only where the tenant declares any — the Subtask kinds the code
// starts itself. It never asks which Measurements to send, and it never asks
// how to read a supplier's response: an Event Type that reads one and declares
// no shape is answered by the Blueprint, with a diagnostic carrying the
// request that declares it (#576). The draft preview is the admin's, and is
// offered to nobody else.

import { ErrorCard } from "@/components/shared/error-card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { tenantDefinedLabel } from "@/lib/localisation";
import { CODE_TARGET_VALUES } from "@/lib/vocabulary";

import { useEventTypes, useKindsOfWork } from "../api/queries";
import type { EventTypeChoice, KindChoice } from "../api/types";
import {
  DEFAULT_TARGET,
  MAX_SELECTED,
  type CodeBuilderSearch,
} from "../lib/code-builder-search";
import { altitudeLabel, codeTargetLabel, declarationStatusLabel } from "../lib/code-builder-words";

const LEGEND = "text-[12px] font-medium text-text-primary";
const HINT = "text-[12px] text-text-secondary";

/** A set of keys with one added or taken away, as the URL keeps it. */
function toggled(keys: readonly string[] | undefined, key: string, on: boolean): string[] | undefined {
  const next = new Set(keys ?? []);
  if (on) next.add(key);
  else next.delete(key);
  return next.size > 0 ? [...next].sort() : undefined;
}

/** Why a selected key is not among the choices offered, if it is not. */
function notOffered(key: string, all: readonly { key: string; retired?: boolean }[]): string {
  const found = all.find((choice) => choice.key === key);
  return found?.retired ? "retired" : "not declared";
}

export function ConfigureStage({
  search,
  onSearchChange,
  offersDraftPreview,
}: {
  search: CodeBuilderSearch;
  onSearchChange: (next: CodeBuilderSearch) => void;
  /** True only for a member KNOWN to be an admin (`roleIsKnownToMeet`). */
  offersDraftPreview: boolean;
}) {
  const kinds = useKindsOfWork();
  const eventTypes = useEventTypes();
  const target = search.target ?? DEFAULT_TARGET;

  return (
    <div className="space-y-5">
      <fieldset className="space-y-1.5">
        <legend className={LEGEND}>Target</legend>
        <div className="flex flex-wrap gap-4">
          {CODE_TARGET_VALUES.map((value) => (
            <label key={value} className="flex items-center gap-2 text-[13px] text-text-primary">
              <input
                type="radio"
                name="code-builder-target"
                value={value}
                checked={target === value}
                onChange={() => onSearchChange({ ...search, target: value })}
              />
              {codeTargetLabel(value)}
            </label>
          ))}
        </div>
      </fieldset>

      {kinds.isPending ? (
        <Skeleton className="h-16 w-full" />
      ) : kinds.isError ? (
        <ErrorCard
          error={kinds.error}
          title="Couldn't load your kinds of work"
          onRetry={() => void kinds.refetch()}
        />
      ) : (
        <>
          <KindQuestion kinds={kinds.data} search={search} onSearchChange={onSearchChange} />
          <SubtaskQuestion kinds={kinds.data} search={search} onSearchChange={onSearchChange} />
        </>
      )}

      {eventTypes.isPending ? (
        <Skeleton className="h-24 w-full" />
      ) : eventTypes.isError ? (
        <ErrorCard
          error={eventTypes.error}
          title="Couldn't load your Event Types"
          onRetry={() => void eventTypes.refetch()}
        />
      ) : (
        <EventTypeQuestion
          eventTypes={eventTypes.data}
          search={search}
          onSearchChange={onSearchChange}
        />
      )}

      {offersDraftPreview && (
        <div className="space-y-1 rounded-md border border-dashed border-border p-3">
          <label className="flex items-center gap-2 text-[13px] font-medium text-text-primary">
            <input
              type="checkbox"
              checked={search.draft_preview === true}
              onChange={(event) =>
                onSearchChange({
                  ...search,
                  draft_preview: event.target.checked ? true : undefined,
                })
              }
            />
            Draft preview — not production-ready
          </label>
          <p className={HINT}>
            Admins only. Resolves from draft declarations instead of published
            ones. It stores nothing, has no configuration fingerprint, and can
            never be verified.
          </p>
        </div>
      )}
    </div>
  );
}

function KindQuestion({
  kinds,
  search,
  onSearchChange,
}: {
  kinds: readonly KindChoice[];
  search: CodeBuilderSearch;
  onSearchChange: (next: CodeBuilderSearch) => void;
}) {
  const offered = kinds.filter((kind) => kind.kind === "task" && !kind.retired);
  const selected = search.task_type;
  const stray = selected !== undefined && !offered.some((kind) => kind.key === selected);
  return (
    <div className="space-y-1.5">
      <label className="block space-y-1.5">
        <span className={LEGEND}>Kind of work</span>
        <select
          className="block w-full max-w-sm rounded-md border border-border bg-bg-surface px-2 py-1.5 text-[13px]"
          value={selected ?? ""}
          onChange={(event) =>
            onSearchChange({ ...search, task_type: event.target.value || undefined })
          }
        >
          <option value="">None selected</option>
          {offered.map((kind) => (
            <option key={kind.key} value={kind.key}>
              {tenantDefinedLabel(kind.key)}
            </option>
          ))}
          {stray && (
            <option value={selected}>
              {`${selected} (${notOffered(selected, kinds)})`}
            </option>
          )}
        </select>
      </label>
      {offered.length === 0 && (
        <p className={HINT}>No kinds of work are declared yet. They are declared on Tasks.</p>
      )}
    </div>
  );
}

function SubtaskQuestion({
  kinds,
  search,
  onSearchChange,
}: {
  kinds: readonly KindChoice[];
  search: CodeBuilderSearch;
  onSearchChange: (next: CodeBuilderSearch) => void;
}) {
  const offered = kinds.filter((kind) => kind.kind === "subtask" && !kind.retired);
  const selected = search.subtask_types ?? [];
  const strays = selected.filter((key) => !offered.some((kind) => kind.key === key));
  // Asked only where it applies: a tenant with no Subtask kinds has nothing
  // to choose, unless the URL already names one.
  if (offered.length === 0 && strays.length === 0) return null;
  return (
    <fieldset className="space-y-1.5">
      <legend className={LEGEND}>{`${altitudeLabel("subtask")} kinds it starts itself`}</legend>
      <p className={HINT}>Only those your code starts explicitly. Leave this empty otherwise.</p>
      <div className="flex flex-wrap gap-x-4 gap-y-1.5">
        {[...offered.map((kind) => kind.key), ...strays].map((key) => (
          <label key={key} className="flex items-center gap-2 text-[13px] text-text-primary">
            <input
              type="checkbox"
              checked={selected.includes(key)}
              disabled={!selected.includes(key) && selected.length >= MAX_SELECTED}
              onChange={(event) =>
                onSearchChange({
                  ...search,
                  subtask_types: toggled(search.subtask_types, key, event.target.checked),
                })
              }
            />
            <span className="font-mono text-[12px]">{tenantDefinedLabel(key)}</span>
            {strays.includes(key) && (
              <span className={HINT}>{`(${notOffered(key, kinds)})`}</span>
            )}
          </label>
        ))}
      </div>
    </fieldset>
  );
}

function EventTypeQuestion({
  eventTypes,
  search,
  onSearchChange,
}: {
  eventTypes: readonly EventTypeChoice[];
  search: CodeBuilderSearch;
  onSearchChange: (next: CodeBuilderSearch) => void;
}) {
  const selected = search.event_types ?? [];
  const strays = selected.filter((key) => !eventTypes.some((row) => row.key === key));
  const keys = [...eventTypes.map((row) => row.key), ...strays];
  return (
    <fieldset className="space-y-1.5">
      <legend className={LEGEND}>Event Types</legend>
      <p className={HINT}>
        What happens inside the work. The Measurements each one sends, and how
        it is costed, are read from its declaration.
      </p>
      {keys.length === 0 ? (
        <p className={HINT}>No Event Types are declared yet.</p>
      ) : (
        <div className="flex flex-wrap gap-x-4 gap-y-1.5">
          {keys.map((key) => {
            const row = eventTypes.find((choice) => choice.key === key);
            return (
              <label key={key} className="flex items-center gap-2 text-[13px] text-text-primary">
                <input
                  type="checkbox"
                  checked={selected.includes(key)}
                  disabled={!selected.includes(key) && selected.length >= MAX_SELECTED}
                  onChange={(event) =>
                    onSearchChange({
                      ...search,
                      event_types: toggled(search.event_types, key, event.target.checked),
                    })
                  }
                />
                <span className="font-mono text-[12px]">{tenantDefinedLabel(key)}</span>
                {row === undefined ? (
                  <span className={HINT}>(not declared)</span>
                ) : (
                  row.declaration_status !== "published" && (
                    <Badge variant="outline">{declarationStatusLabel(row.declaration_status)}</Badge>
                  )
                )}
              </label>
            );
          })}
        </div>
      )}
    </fieldset>
  );
}
