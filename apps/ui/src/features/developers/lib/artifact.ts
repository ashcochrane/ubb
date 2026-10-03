// Generate: a Blueprint becomes files, in the browser (#579).
//
// `ubb-codegen`'s `render` is the only thing that writes integration code; the
// console never holds a template of its own (#156 §10.4). It is a pure
// function over the Blueprint and takes milliseconds, so the page calls it
// synchronously, once per Blueprint (`useMemo` at the call site).
//
// ⚠ IT REFUSES A DOCUMENT IT CANNOT READ, by throwing `BlueprintNotRenderable`
// — a schema or renderer contract it was not written to, or a token that
// breaks what the contract promises (ADR-0016 §7). That is caught here and
// becomes something the page SHOWS. Anything else thrown is a defect in the
// renderer or the page, and is left to reach the route's error boundary
// rather than be dressed up as a refusal.

import { BlueprintNotRenderable, render, type FileKind, type RenderedFile } from "ubb-codegen";

import type { Blueprint, BlueprintCall } from "../api/types";

export type { FileKind, RenderedFile };

export type Artifact =
  | { readonly kind: "files"; readonly files: readonly RenderedFile[] }
  | { readonly kind: "refused"; readonly reason: string };

export function artifactOf(blueprint: Blueprint): Artifact {
  try {
    return { kind: "files", files: render(blueprint) };
  } catch (error) {
    if (error instanceof BlueprintNotRenderable) {
      return { kind: "refused", reason: error.message };
    }
    throw error;
  }
}

/**
 * What each kind of file is called on the page, in the order the page shows
 * them. Total over the renderer's own type, so a kind it starts writing is a
 * `tsc` failure here rather than a file the page silently leaves out.
 */
export const FILE_KIND_TITLES: Readonly<Record<FileKind, string>> = {
  module: "The integration module",
  call_site: "Where each call goes in your code",
  environment_example: "Environment",
  verify_script: "Checking the environment",
  request_preview: "The request each call sends",
};

function isFileKind(key: string): key is FileKind {
  return Object.hasOwn(FILE_KIND_TITLES, key);
}

/** Every kind of file, in the order the page shows them. */
export const FILE_KINDS: readonly FileKind[] = Object.keys(FILE_KIND_TITLES).filter(isFileKind);

export interface CallPreview {
  readonly call: BlueprintCall;
  /** The preview of this call's request, or null where none can be paired. */
  readonly preview: RenderedFile | null;
}

/**
 * Each call beside the preview of the request it sends (ADR-0017 §7: one
 * preview a call, because the page shows a call at a time).
 *
 * Paired by position — the renderer writes previews in call order — and each
 * pair CHECKED by the operation the preview states. If the counts differ or a
 * single pair disagrees, nothing is paired and every preview is returned
 * unpaired: a preview under the wrong call would describe a request that call
 * does not send.
 */
export function previewsByCall(
  blueprint: Blueprint,
  files: readonly RenderedFile[],
): { paired: CallPreview[]; unpaired: RenderedFile[] } {
  const previews = files.filter((file) => file.kind === "request_preview");
  const agrees =
    previews.length === blueprint.calls.length &&
    blueprint.calls.every((call, index) =>
      previews[index]?.contents.includes(`operation_id = ${JSON.stringify(call.operation_id)}`),
    );
  if (!agrees) {
    return {
      paired: blueprint.calls.map((call) => ({ call, preview: null })),
      unpaired: previews,
    };
  }
  return {
    paired: blueprint.calls.map((call, index) => ({ call, preview: previews[index] ?? null })),
    unpaired: [],
  };
}

/** A file's name as a download: its own name, without the folder it sits in. */
export function downloadName(path: string): string {
  return path.slice(path.lastIndexOf("/") + 1);
}
