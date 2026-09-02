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

export type { PricingMode, TaskTypeKind } from "@/lib/vocabulary";

/**
 * How the runs list is narrowed.
 *
 * Only the two filters this feature reads today. The route also takes a
 * customer, which the runs surface (#424) will add when it has a reader for
 * it — a filter the mock would have to ignore is worse than one it does not
 * offer.
 */
export interface RunsFilters {
  task_type?: string;
  status?: string;
}
