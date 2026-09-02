// Type aliases over the generated schema map for the tasks feature.
//
// A unit of work is a KERNEL concept and its whole surface sits at the root
// prefix (#409, #414): the kind-of-work registry at `/task-types` and the
// lifecycle at `/tasks`. So every alias here comes from the root schemas, and
// none from a product's.
//
// The canonical value sets are the REGISTRY'S, reached through the generated
// vocabulary rather than re-derived from the contract — the contract carries
// the same two words for `pricing_mode`, but making it the authority on a set
// the registry owns is the drift the consumer gates exist to abolish.

import type { RootSchemas } from "@/api/types";
import type { TaskStatus } from "@/lib/vocabulary";

/** One declared kind of work, as the registry reports it. */
export type KindOfWork = RootSchemas["TaskTypeOut"];

/** One declaration, as a caller sends it — the whole vocabulary goes each time. */
export type KindOfWorkDeclaration = RootSchemas["TaskTypeIn"];

/** The body of the idempotent whole-vocabulary declare. */
export type DeclareKindsBody = RootSchemas["TaskTypeRegistryIn"];

/** One top-level run of a kind of work, with its materialized rollups. */
export type RunRow = RootSchemas["TaskOut"];

/** A page of runs, in the house cursor envelope. */
export type RunsPage = RootSchemas["PaginatedTasks"];

/**
 * One run with the work contained in it — every piece, not a page (see
 * `getRun` in `./api`). A piece of contained work is the same shape with a
 * parent and nothing contained in it.
 */
export type RunDetail = RootSchemas["TaskDetailOut"];

export type { PricingMode, TaskStatus, TaskTypeKind } from "@/lib/vocabulary";

/**
 * A declaration's identity is the word AND the altitude, not the word alone:
 * one key may name a kind of work at either altitude, and the two are
 * different declarations with different policy (`TaskType`'s uniqueness is
 * `(tenant, kind, key)`). Here rather than in `lib/`, because the mock needs
 * the same rule and a mock does not reach into its feature's lib.
 */
export function sameDeclaration(
  a: Pick<KindOfWork, "kind" | "key">,
  b: Pick<KindOfWork, "kind" | "key">,
): boolean {
  return a.kind === b.kind && a.key === b.key;
}

/**
 * How the runs list is narrowed.
 *
 * The kind of work and the lifecycle state — the two the runs surface reads
 * (#424). The route also takes a customer, which arrives when a surface has
 * a reader for it: a filter the mock would have to ignore is worse than one
 * it does not offer.
 */
export interface RunsFilters {
  task_type?: string;
  status?: TaskStatus;
}
