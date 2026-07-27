import type { PlatformSchemas } from "./types";

export class ApiError extends Error {
  readonly status?: number;
  readonly code?: string;

  constructor(message: string, problem?: Partial<PlatformSchemas["ProblemOut"]>) {
    super(message);
    this.name = "ApiError";
    this.status = problem?.status;
    this.code = problem?.code;
  }
}

function readProblem(error: unknown): Partial<PlatformSchemas["ProblemOut"]> | undefined {
  if (typeof error !== "object" || error === null) return undefined;
  const problem: Partial<PlatformSchemas["ProblemOut"]> = {};
  if ("detail" in error && typeof error.detail === "string") problem.detail = error.detail;
  if ("title" in error && typeof error.title === "string") problem.title = error.title;
  if ("status" in error && typeof error.status === "number") problem.status = error.status;
  if ("code" in error && typeof error.code === "string") problem.code = error.code;
  return problem;
}

export function apiError(error: unknown, fallback: string): ApiError {
  const problem = readProblem(error);
  const message = problem?.detail || problem?.title || fallback;
  return new ApiError(message, problem);
}

export function requireData<T>(
  result: { data?: T; error?: unknown },
  fallback: string,
): T {
  if (result.error !== undefined) throw apiError(result.error, fallback);
  if (result.data === undefined) throw new ApiError(fallback);
  return result.data;
}

export function errorMessage(error: unknown, fallback = "Something went wrong"): string {
  return error instanceof Error && error.message ? error.message : fallback;
}
