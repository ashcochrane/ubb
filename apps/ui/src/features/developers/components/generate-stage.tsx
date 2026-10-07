// Generate: the files, written in the browser by `ubb-codegen` (#579).
//
// The copy action says *Copy scaffold* until the verdict is `complete`, and the
// files' own header says the same, because a label is lost on copy. A request
// preview is documentation of one request a Shell file sends: it carries no
// verdict, so none is shown beside it (ADR-0017 §7). The `.env.example` asks
// for the API's address and the page fills in none (ADR-0016 §8).
//
// What the developer last took is the URL's `held` fingerprint: copying or
// downloading a file of a stored Blueprint records it, and a Blueprint that
// resolves to another fingerprint — the configuration changed, or the
// selection did — says the files held are stale.

import type { UseQueryResult } from "@tanstack/react-query";
import { useMemo } from "react";

import { Skeleton } from "@/components/ui/skeleton";

import type { Blueprint } from "../api/types";
import {
  artifactOf,
  FILE_KIND_TITLES,
  FILE_KINDS,
  previewsByCall,
  type RenderedFile,
} from "../lib/artifact";
import { copyActionLabel, stalenessOf } from "../lib/blueprint";
import { callHeading, readinessLabel, STALE_FILES_WARNING } from "../lib/code-builder-words";
import { FilePanel } from "./file-panel";
import { Fingerprint } from "./fingerprint";

/** The kinds a developer takes as the integration; previews are shown by call. */
const TAKEN_KINDS = FILE_KINDS.filter((kind) => kind !== "request_preview");

export function GenerateStage({
  query,
  held,
  onTaken,
}: {
  query: UseQueryResult<Blueprint>;
  held: string | undefined;
  /** The fingerprint of a stored Blueprint whose files were just taken. */
  onTaken: (fingerprint: string) => void;
}) {
  const blueprint = query.data;
  const artifact = useMemo(
    () => (blueprint === undefined ? null : artifactOf(blueprint)),
    [blueprint],
  );

  if (query.isPending) return <Skeleton className="h-40 w-full" />;
  if (blueprint === undefined || artifact === null) {
    return (
      <p className="text-[12px] text-text-secondary">
        Nothing to generate until the Blueprint resolves.
      </p>
    );
  }
  if (artifact.kind === "refused") {
    return (
      <div role="alert" className="space-y-1 rounded-md border border-border p-4">
        <p className="text-[13px] font-medium text-text-primary">
          This console cannot turn this Blueprint into files.
        </p>
        <p className="text-[12px] text-text-secondary">{artifact.reason}</p>
        <p className="text-[12px] text-text-secondary">
          The Blueprint above is still what the API resolved; a newer console can
          generate from it.
        </p>
      </div>
    );
  }

  const fingerprint = blueprint.configuration_fingerprint ?? null;
  const took = fingerprint === null ? undefined : () => onTaken(fingerprint);
  const copyLabel = copyActionLabel(blueprint.readiness);
  const { paired, unpaired } = previewsByCall(blueprint, artifact.files);
  const previewed = paired.some(({ preview }) => preview !== null) || unpaired.length > 0;

  return (
    // Keyed on each resolution, a draft preview's included: regenerated files
    // are new files, so nothing a panel showed about the last ones — a
    // "Copied" — carries over to them.
    <div key={query.dataUpdatedAt} className="space-y-5" aria-busy={query.isPlaceholderData}>
      <Held held={held} blueprint={blueprint} />
      <p className="text-[12px] text-text-secondary">
        {`${readinessLabel(blueprint.readiness)}. `}
        {blueprint.readiness === "complete"
          ? "Every call these files make resolves against what you have declared."
          : "A call that is not ready refuses to run, and says why."}
      </p>
      {TAKEN_KINDS.map((kind) => (
        <FileGroup
          key={kind}
          title={FILE_KIND_TITLES[kind]}
          files={artifact.files.filter((file) => file.kind === kind)}
          copyLabel={copyLabel}
          onTaken={took}
        />
      ))}
      {previewed && (
        <section aria-label={FILE_KIND_TITLES.request_preview} className="space-y-2">
          <h3 className="text-[12px] font-medium text-text-primary">
            {FILE_KIND_TITLES.request_preview}
          </h3>
          <p className="text-[12px] text-text-secondary">
            Documentation, not a file to run: each request as the Shell file sends
            it, a call at a time.
          </p>
          {paired.map(({ call, preview }, index) => {
            if (preview === null) return null;
            return (
              <div key={`${call.operation_id}:${index}`} className="space-y-1">
                <h4 className="text-[12px] text-text-secondary">{callHeading(call)}</h4>
                <FilePanel file={preview} copyLabel="Copy request preview" />
              </div>
            );
          })}
          {unpaired.map((preview) => (
            <FilePanel key={preview.path} file={preview} copyLabel="Copy request preview" />
          ))}
        </section>
      )}
    </div>
  );
}

function FileGroup({
  title,
  files,
  copyLabel,
  onTaken,
}: {
  title: string;
  files: readonly RenderedFile[];
  copyLabel: string;
  onTaken: (() => void) | undefined;
}) {
  if (files.length === 0) return null;
  return (
    <section aria-label={title} className="space-y-2">
      <h3 className="text-[12px] font-medium text-text-primary">{title}</h3>
      {files.map((file) => (
        <FilePanel key={file.path} file={file} copyLabel={copyLabel} onTaken={onTaken} />
      ))}
    </section>
  );
}

function Held({ held, blueprint }: { held: string | undefined; blueprint: Blueprint }) {
  const staleness = stalenessOf(held, blueprint);
  switch (staleness.kind) {
    case "nothing_held":
      return null;
    case "current":
      return (
        <p role="status" className="text-[12px] text-text-secondary">
          These are the files you took: they were generated from this Blueprint.
        </p>
      );
    case "stale":
      // ⚠ CAUSE-NEUTRAL (owner ruling on #600). Two fingerprints differ: the
      // configuration may have changed, or the selection may have. The page
      // knows only that the files in hand do not describe this Blueprint, and
      // says no more than that.
      //
      // A draft preview has no fingerprint and shows none — not even the one
      // the files taken carry, which belongs to another Blueprint.
      return (
        <div role="status" className="space-y-1 rounded-md border border-border p-3" data-stale>
          <p className="text-[13px] font-medium text-text-primary">{STALE_FILES_WARNING}</p>
          {staleness.current === null ? (
            <p className="text-[12px] text-text-secondary">
              This is a draft preview, which no file is ever current against: the files
              you took were generated from a published Blueprint.
            </p>
          ) : (
            <p className="text-[12px] text-text-secondary">
              They were generated from <Fingerprint value={staleness.held} />; the current
              Blueprint is <Fingerprint value={staleness.current} />. The files below are
              generated from the current one.
            </p>
          )}
        </div>
      );
  }
}
