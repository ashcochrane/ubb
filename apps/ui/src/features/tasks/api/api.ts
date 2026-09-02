// Real API adapter for the tasks feature. Every call is `unwrap`ed so a
// non-2xx surfaces as an `ApiProblem` the components can branch on.

import { rootApi } from "@/api/client";
import { unwrap } from "@/api/problem";

import type {
  DeclareKindsBody,
  KindOfWork,
  RunsFilters,
  RunsPage,
} from "./types";

/**
 * Every kind of work the workspace has declared, retired ones included.
 *
 * Unwrapped ONCE here so the feature holds a list rather than an envelope
 * (#372's lesson): a component reading `data.task_types` would put the wire's
 * property name on every screen that renders the registry.
 */
export async function listKinds(): Promise<KindOfWork[]> {
  return unwrap(await rootApi.GET("/task-types")).task_types;
}

/**
 * Declare the whole vocabulary — every kind of work, every time.
 *
 * The route is an idempotent PUT over the collection: a kind of work it is
 * not told about is not touched, but a kind it IS told about has its ceiling,
 * its windows and its required grouping fields replaced by what the body
 * says. So a caller must send every standing declaration verbatim beside the
 * one it is changing, and `declarationBody` in `../lib/kinds` is the one
 * place that assembles such a body. Admin floor.
 */
export async function declareKinds(body: DeclareKindsBody): Promise<KindOfWork[]> {
  return unwrap(await rootApi.PUT("/task-types", { body })).task_types;
}

/** Top-level runs, newest first; contained work belongs to its parent. */
export async function listRuns(
  filters: RunsFilters,
  cursor: string | undefined,
): Promise<RunsPage> {
  return unwrap(
    await rootApi.GET("/tasks", {
      params: {
        query: {
          cursor,
          task_type: filters.task_type,
        },
      },
    }),
  );
}
