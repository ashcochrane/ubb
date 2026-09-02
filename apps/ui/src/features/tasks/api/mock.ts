// Mock implementation — same exported signatures as ./api.ts, over the
// fixture registry. The registry keeps session state (module-level) so a
// declaration behaves like the real idempotent PUT: what you sent back is what
// you read next, and what you did not send is untouched.

import { ApiProblem } from "@/api/problem";
import { mockDelay } from "@/lib/api-provider";
import { TASK_TYPE_KIND_VALUES } from "@/lib/vocabulary";

import { MOCK_CONTAINED, MOCK_KINDS, MOCK_RUNS } from "./mock-data";
import {
  sameDeclaration,
  type DeclareKindsBody,
  type KindOfWork,
  type KindOfWorkDeclaration,
  type RunDetail,
  type RunsFilters,
  type RunsPage,
} from "./types";

function copyOf(kind: KindOfWork): KindOfWork {
  return { ...kind, required_dimensions: [...kind.required_dimensions] };
}

let kinds: KindOfWork[] = MOCK_KINDS.map(copyOf);

/** Test-only: put the registry back to the fixture. */
export function resetTasksMockState(): void {
  kinds = MOCK_KINDS.map(copyOf);
}

export async function listKinds(): Promise<KindOfWork[]> {
  await mockDelay();
  return kinds.map(copyOf);
}

/**
 * The server's rules for one declaration, mirrored so the console is refused
 * by the mock exactly where it would be refused for real
 * (`api/v1/task_type_endpoints.py::declare_task_types`):
 *
 *   - a kind the registry does not recognise → `422 validation_error`;
 *   - a regime that differs from a standing declaration's →
 *     `409 pricing_mode_frozen`, naming the regime the row holds;
 *   - an omitted regime leaves a standing declaration as it is and declares a
 *     new one `event_priced` — the COLUMN's default, not a value invented here;
 *   - `retired: true` stamps the instant the kind stopped being offered,
 *     `retired: false` clears it, and an omitted `retired` changes nothing.
 *
 * Everything else — the ceiling, the two windows, the required grouping
 * fields — is replaced by what the body says, which is why a caller sends
 * every standing declaration verbatim (see `declareKinds` in `./api`).
 *
 * Applied to the live list one declaration at a time, so a body naming one
 * declaration twice sees its own first write, as the route does.
 */
function apply(declaration: KindOfWorkDeclaration, now: string): void {
  const kind = declaration.kind ?? "task";
  if (!(TASK_TYPE_KIND_VALUES as readonly string[]).includes(kind)) {
    throw new ApiProblem({
      status: 422,
      code: "validation_error",
      title: "Unprocessable Content",
      detail: `invalid kind '${kind}'`,
    });
  }
  const standing = kinds.find((row) => sameDeclaration(row, { kind, key: declaration.key }));
  const requested = declaration.pricing_mode ?? null;
  if (standing && requested !== null && requested !== standing.pricing_mode) {
    throw new ApiProblem({
      status: 409,
      code: "pricing_mode_frozen",
      title: "Conflict",
      detail:
        `${declaration.key} is already declared as sold ${standing.pricing_mode} and that ` +
        `cannot change; retire it and declare a replacement under a new key.`,
      extensions: { key: declaration.key, kind, pricing_mode: standing.pricing_mode },
    });
  }
  const wasRetired = standing?.retired ?? false;
  const retired = declaration.retired ?? wasRetired;
  const retiredAt =
    declaration.retired === true
      ? (standing?.retired_at ?? now)
      : declaration.retired === false
        ? null
        : (standing?.retired_at ?? null);
  const written: KindOfWork = {
    key: declaration.key,
    kind,
    pricing_mode: standing?.pricing_mode ?? requested ?? "event_priced",
    default_provider_cost_limit_micros: declaration.default_provider_cost_limit_micros ?? null,
    silence_window_seconds: declaration.silence_window_seconds ?? null,
    absolute_deadline_seconds: declaration.absolute_deadline_seconds ?? null,
    required_dimensions: [...(declaration.required_dimensions ?? [])],
    retired,
    retired_at: retiredAt,
  };
  if (standing) {
    kinds = kinds.map((row) => (row === standing ? written : row));
  } else {
    kinds = [...kinds, written];
  }
}

export async function declareKinds(body: DeclareKindsBody): Promise<KindOfWork[]> {
  await mockDelay();
  // The whole body is one transaction on the server: a refusal on the fourth
  // declaration leaves none of the first three behind. Same here.
  const before = kinds;
  const now = new Date().toISOString();
  try {
    for (const declaration of body.task_types) apply(declaration, now);
  } catch (error) {
    kinds = before;
    throw error;
  }
  return kinds.map(copyOf);
}

/**
 * Top-level runs, narrowed the way the route narrows them.
 *
 * The fixture is one page; the cursor is accepted for the signature and
 * never needed.
 */
export async function listRuns(
  filters: RunsFilters,
  _cursor: string | undefined,
): Promise<RunsPage> {
  await mockDelay();
  const rows = MOCK_RUNS.filter(
    (row) =>
      (filters.task_type === undefined || row.task_type === filters.task_type) &&
      (filters.status === undefined || row.status === filters.status),
  );
  return { data: rows.map((row) => ({ ...row })), has_more: false, next_cursor: null };
}

/**
 * One run with everything contained in it, as the route answers: the row
 * plus its children, oldest first, and `404 not_found` for an id nobody has.
 * A piece of contained work is a run too, and answers with nothing contained
 * in it.
 */
export async function getRun(taskId: string): Promise<RunDetail> {
  await mockDelay();
  const everyRow = [...MOCK_RUNS, ...Object.values(MOCK_CONTAINED).flat()];
  const found = everyRow.find((row) => row.task_id === taskId);
  if (!found) {
    throw new ApiProblem({
      status: 404,
      code: "not_found",
      title: "Not Found",
      detail: `No unit of work ${taskId}.`,
    });
  }
  const contained = MOCK_CONTAINED[taskId] ?? [];
  return { ...found, subtasks: contained.map((row) => ({ ...row })) };
}
