// The Blueprints the mock answers with: the platform's own (#579).
//
// ⚠ NOT ONE IS WRITTEN HERE. `apps/codegen/fixtures/blueprints/*.json` are
// written by the platform — `test_the_renderers_fixtures_are_what_the_platform_
// answers.py` resolves each through the routes and holds file == answer — and
// the renderer's suite reads the same files. A Blueprint built by hand for the
// console is where a page and the contract silently part: it would carry
// whatever this file's author believed a Blueprint looks like, and the page
// would be tested against that belief.
//
// ⚠ EACH FIXTURE IS ITS OWN TENANT. The platform test configures a fresh
// tenant per fixture, so one Event Type key can be `complete` in one fixture
// and `blocked` in another. The mock therefore answers a selection with the
// Blueprint the platform wrote FOR THAT SELECTION, and two selections may come
// from differently configured tenants. It never stitches calls from several
// fixtures into one document — that would be resolving, which is the server's.
//
// Loaded lazily: the files are ~340 KB, and only mock mode ever reads them.

import { CODE_TARGET_VALUES, INTEGRATION_READINESS_VALUES } from "@/lib/vocabulary";

import { roleOf, subjectOf, type CallRole } from "../lib/blueprint";
import type {
  Blueprint,
  BlueprintSelection,
  EventTypeChoice,
  KindChoice,
} from "./types";

const LOADERS = import.meta.glob<unknown>(
  "../../../../../codegen/fixtures/blueprints/*.json",
  { import: "default" },
);

function nameOf(path: string): string {
  return path.slice(path.lastIndexOf("/") + 1).replace(/\.json$/, "");
}

const LOADER_BY_NAME = new Map(
  Object.entries(LOADERS).map(([path, load]) => [nameOf(path), load]),
);

/** Every platform-written Blueprint, by its file's name. */
export const BLUEPRINT_FIXTURE_NAMES: readonly string[] = [...LOADER_BY_NAME.keys()].sort();

function isOneOf<T extends string>(values: readonly T[], value: unknown): value is T {
  return values.some((member) => member === value);
}

/**
 * The document's shape, checked at the one place a file becomes a Blueprint.
 * A JSON import is typed by its contents (`"python_sdk"` reads as `string`),
 * so this is what lets the mock hand the page a typed document without a
 * cast — and what says so if a fixture ever stops being one.
 */
export function isBlueprint(value: unknown): value is Blueprint {
  if (typeof value !== "object" || value === null) return false;
  const calls: unknown = Reflect.get(value, "calls");
  const diagnostics: unknown = Reflect.get(value, "diagnostics");
  return (
    typeof Reflect.get(value, "schema_version") === "number" &&
    typeof Reflect.get(value, "renderer_contract_version") === "number" &&
    isOneOf(CODE_TARGET_VALUES, Reflect.get(value, "target")) &&
    isOneOf(INTEGRATION_READINESS_VALUES, Reflect.get(value, "readiness")) &&
    Array.isArray(calls) &&
    calls.every(
      (call: unknown) =>
        typeof call === "object" &&
        call !== null &&
        typeof Reflect.get(call, "operation_id") === "string" &&
        isOneOf(INTEGRATION_READINESS_VALUES, Reflect.get(call, "readiness")) &&
        Array.isArray(Reflect.get(call, "arguments")),
    ) &&
    Array.isArray(diagnostics)
  );
}

/** One platform-written Blueprint, by name. */
export async function loadBlueprintFixture(name: string): Promise<Blueprint> {
  const load = LOADER_BY_NAME.get(name);
  if (load === undefined) throw new Error(`no platform-written Blueprint named ${name}`);
  const document = await load();
  if (!isBlueprint(document)) throw new Error(`${name} is not an Integration Blueprint`);
  return document;
}

/**
 * The selection a Blueprint answers, read back off the document: its target,
 * whether it is a draft preview (no fingerprint), the kind its Task start
 * names, the kinds its Subtask starts name, and the Event Types it records.
 */
export function selectionAnsweredBy(blueprint: Blueprint): BlueprintSelection {
  const subjects = (role: CallRole) =>
    blueprint.calls.flatMap((call) => {
      const subject = roleOf(call) === role ? subjectOf(call) : null;
      return subject === null ? [] : [subject];
    });
  return {
    target: blueprint.target,
    task_type: subjects("start_task")[0] ?? null,
    event_types: subjects("record_usage").sort(),
    subtask_types: subjects("start_subtask").sort(),
    draft_preview: blueprint.configuration_fingerprint === null,
  };
}

/** One canonical spelling of a selection, so equal selections are equal keys. */
export function selectionKey(selection: BlueprintSelection): string {
  return JSON.stringify([
    selection.target,
    selection.draft_preview ?? false,
    selection.task_type ?? null,
    [...(selection.subtask_types ?? [])].sort(),
    [...(selection.event_types ?? [])].sort(),
  ]);
}

// ---------------------------------------------------------------------------
// The mock tenant's configuration, and the one change to it the set can show

/**
 * Two platform-written Blueprints answer ONE selection — Shell,
 * `report_generation`, `chat.completion` — because the platform wrote one
 * before and one after `chat.completion` declares a response shape a shell can
 * read: `shell-unreadable-shape` is blocked on its Python-object shape (with
 * the request that revises it), `shell-calculated-cost` is complete. That pair
 * is the mock's configuration fix, and the only one it can show without
 * writing a Blueprint of its own.
 *
 * After the revision the mock answers no other selection naming the revised
 * Event Type: the platform wrote no Blueprint for those under the revised
 * declaration, and answering the old one would hand the page a document whose
 * configuration no longer holds.
 */
export const THE_REVISION = {
  eventType: "chat.completion",
  before: "shell-unreadable-shape",
  after: "shell-calculated-cost",
} as const;

let revised = false;

/** Mock only: revise the mock tenant's configuration as `THE_REVISION` says. */
export function reviseMockConfiguration(): void {
  revised = true;
}

/** Mock only: the configuration as first declared. */
export function resetMockConfiguration(): void {
  revised = false;
}

async function everyFixture(): Promise<Array<readonly [string, Blueprint]>> {
  return Promise.all(
    BLUEPRINT_FIXTURE_NAMES.map(async (name) => [name, await loadBlueprintFixture(name)] as const),
  );
}

function answersNow(name: string, blueprint: Blueprint): boolean {
  if (name === THE_REVISION.after) return revised;
  if (!revised) return true;
  return !(selectionAnsweredBy(blueprint).event_types ?? []).includes(THE_REVISION.eventType);
}

/**
 * The Blueprint the mock answers each selection with, as the configuration
 * stands. Two answers to one selection is a fixture set this mock cannot read
 * honestly, and says so rather than picking one.
 */
export async function mockAnswers(): Promise<Map<string, Blueprint>> {
  const answers = new Map<string, Blueprint>();
  for (const [name, blueprint] of await everyFixture()) {
    if (!answersNow(name, blueprint)) continue;
    const key = selectionKey(selectionAnsweredBy(blueprint));
    if (answers.has(key)) {
      throw new Error(`two platform-written Blueprints answer one selection: ${key}`);
    }
    answers.set(key, blueprint);
  }
  return answers;
}

/**
 * What Configure offers in mock mode: every kind and Event Type a
 * platform-written Blueprint the mock answers with names, read off that
 * Blueprint's tokens — never declared here. A kind's altitude is the start
 * that names it; an Event Type is a draft where its token states no
 * published revision. A draft preview states no publication for anything, so
 * it declares nothing here.
 */
export async function mockRegistry(): Promise<{
  kinds: KindChoice[];
  eventTypes: EventTypeChoice[];
}> {
  const kinds = new Map<string, KindChoice>();
  const eventTypes = new Map<string, EventTypeChoice>();
  for (const blueprint of (await mockAnswers()).values()) {
    if (blueprint.configuration_fingerprint === null) continue;
    for (const call of blueprint.calls) {
      const key = subjectOf(call);
      if (key === null) continue;
      const role = roleOf(call);
      if ((role === "start_task" || role === "start_subtask") && !kinds.has(key)) {
        kinds.set(key, { key, kind: role === "start_subtask" ? "subtask" : "task", retired: false });
      }
      if (role === "record_usage" && !eventTypes.has(key)) {
        const token = call.arguments.find((argument) => argument.name === "event_type");
        const published = typeof token?.provenance?.published_revision === "number";
        eventTypes.set(key, { key, declaration_status: published ? "published" : "draft" });
      }
    }
  }
  const byKey = <T extends { key: string }>(rows: Iterable<T>) =>
    [...rows].sort((a, b) => a.key.localeCompare(b.key));
  return { kinds: byKey(kinds.values()), eventTypes: byKey(eventTypes.values()) };
}
