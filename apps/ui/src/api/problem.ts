// RFC 9457 problem+json handling for the UBB API.
//
// Every non-2xx response from the backend is (or should be treated as) a
// ProblemOut body: { type, title, status, code, detail, ...extensions }.
// Many operations declare only their 200 in the OpenAPI schema, so the
// generated error types are incomplete — this module is the single place
// that normalises ANY failure (declared or not) into an `ApiProblem`.

import type { PlatformSchemas } from "./types";

type ProblemOut = PlatformSchemas["ProblemOut"];

export class ApiProblem extends Error {
  readonly status: number;
  readonly code: string;
  readonly title: string;
  readonly detail: string | null;
  /** Open-world extension members (e.g. balance_micros) — deliberately unmodeled. */
  readonly extensions: Record<string, unknown>;

  constructor(problem: {
    status: number;
    code: string;
    title: string;
    detail?: string | null;
    extensions?: Record<string, unknown>;
  }) {
    super(problem.detail || problem.title);
    this.name = "ApiProblem";
    this.status = problem.status;
    this.code = problem.code;
    this.title = problem.title;
    this.detail = problem.detail ?? null;
    this.extensions = problem.extensions ?? {};
  }
}

const KNOWN_PROBLEM_KEYS = new Set(["type", "title", "status", "code", "detail"]);

function isProblemShaped(value: unknown): value is ProblemOut & Record<string, unknown> {
  return (
    typeof value === "object" &&
    value !== null &&
    "code" in value &&
    "status" in value &&
    typeof (value as { code: unknown }).code === "string"
  );
}

/**
 * Normalise an openapi-fetch `error` value (plus the raw Response) into an
 * ApiProblem. Handles problem+json bodies, bare error bodies, and network
 * failures alike.
 */
export function toApiProblem(error: unknown, response?: Response): ApiProblem {
  if (error instanceof ApiProblem) return error;
  if (isProblemShaped(error)) {
    const extensions: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(error)) {
      if (!KNOWN_PROBLEM_KEYS.has(key)) extensions[key] = value;
    }
    return new ApiProblem({
      status: error.status,
      code: error.code,
      title: error.title,
      detail: error.detail,
      extensions,
    });
  }
  const status = response?.status ?? 0;
  return new ApiProblem({
    status,
    code: status === 0 ? "network_error" : `http_${status}`,
    title: status === 0 ? "Network error" : `Request failed (${status})`,
    detail:
      error instanceof Error
        ? error.message
        : typeof error === "string"
          ? error
          : null,
  });
}

/**
 * Unwrap an openapi-fetch result: return `data`, or throw an ApiProblem.
 * Use in every feature api.ts so queries/mutations always reject with a
 * typed problem.
 */
export function unwrap<T>(result: {
  data?: T;
  error?: unknown;
  response: Response;
}): T {
  if (result.error !== undefined) {
    throw toApiProblem(result.error, result.response);
  }
  // 2xx with no body (or a body openapi-fetch could not parse).
  return result.data as T;
}

/** Human-readable fallback messages for well-known problem codes. */
const CODE_MESSAGES: Record<string, string> = {
  unauthorized: "Your session is no longer valid. Sign in again.",
  forbidden: "Your role doesn't allow this action.",
  feature_not_enabled: "This product isn't enabled for your workspace.",
  not_found: "That resource no longer exists.",
  conflict: "This conflicts with something that already exists.",
  currency_locked:
    "The workspace currency is locked because money has already been recorded.",
  last_active_key:
    "You can't revoke the last active API key — rotate it instead.",
  invalid_cursor: "This page reference has expired. Reload the list.",
  validation_error: "Some fields are invalid.",
  invalid_config: "This configuration is invalid.",
  unsupported_currency: "That currency isn't supported.",
  stripe_tax_not_active:
    "Stripe Tax isn't active on the connected Stripe account.",
  insufficient_balance: "The balance is too low for this operation.",
  rate_limit_exceeded: "Too many requests — try again shortly.",
  billing_period_closed: "That billing period is closed to changes.",
  service_unavailable: "The service is temporarily unavailable. Try again.",
  internal_error: "Something went wrong on our side.",
  network_error: "Couldn't reach the server. Check your connection.",
};

/** Best human-readable message for a failure (problem-aware). */
export function problemMessage(error: unknown): string {
  if (error instanceof ApiProblem) {
    return error.detail || CODE_MESSAGES[error.code] || error.title;
  }
  if (error instanceof Error && error.message) return error.message;
  return "Something went wrong.";
}

/** True when the failure is a 403 for a product the tenant doesn't have. */
export function isFeatureNotEnabled(error: unknown): boolean {
  return error instanceof ApiProblem && error.code === "feature_not_enabled";
}

/** True when the failure is a role-floor 403. */
export function isForbidden(error: unknown): boolean {
  return error instanceof ApiProblem && error.code === "forbidden";
}

/** True for 404 problems. */
export function isNotFound(error: unknown): boolean {
  return error instanceof ApiProblem && error.status === 404;
}
