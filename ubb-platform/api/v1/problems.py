"""Central problem+json rendering (#78): the nine dialects die here.

One handler layer on the one NinjaAPI turns every error — raised ``Problem``s,
stray ``HttpError``s, request-validation failures, ``Http404``, auth failures,
and unhandled exceptions — into RFC 9457 ``application/problem+json`` with a
registry ``code`` (``core/problems.py``). Nothing below the API layer builds
an error body by hand; endpoints raise, this module renders.

5xx bodies never leak internals: the unhandled-exception handler logs the
traceback server-side and serves a bare ``internal_error`` problem.
"""
import json
import logging

from django.http import Http404, HttpResponse
from ninja.errors import (
    AuthenticationError as NinjaAuthenticationError,
    HttpError,
    ValidationError as NinjaValidationError,
)

from core.problems import PROBLEM_TYPE_BASE, PROBLEMS, Problem

logger = logging.getLogger(__name__)

# Fallback mapping for HttpErrors that predate the conversion (and ninja's own
# internals, e.g. the 400 "Cannot parse request body"). Converted code raises
# Problem directly; this lane keeps any straggler on-dialect.
_CODE_BY_STATUS = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    409: "conflict",
    410: "gone",
    422: "validation_error",
    429: "rate_limit_exceeded",
    503: "service_unavailable",
}


def problem_response(code, detail=None, *, extensions=None, headers=None):
    """Render one problem+json response. Status always comes from the
    registry — a code cannot be served with a foreign status."""
    entry = PROBLEMS[code]
    payload = {
        "type": PROBLEM_TYPE_BASE + code,
        "title": entry["title"],
        "status": entry["status"],
        "code": code,
    }
    if detail is not None:
        payload["detail"] = detail
    if extensions:
        payload.update(extensions)
    response = HttpResponse(
        json.dumps(payload),
        status=entry["status"],
        content_type="application/problem+json",
    )
    for name, value in (headers or {}).items():
        response[name] = value
    return response


def install_problem_handlers(api):
    @api.exception_handler(Problem)
    def _problem(request, exc):
        return problem_response(
            exc.code, exc.detail, extensions=exc.extensions, headers=exc.headers
        )

    @api.exception_handler(HttpError)
    def _http_error(request, exc):
        code = _CODE_BY_STATUS.get(exc.status_code, "internal_error")
        leak_safe = exc.status_code < 500 and not isinstance(
            exc, NinjaAuthenticationError
        )
        return problem_response(code, str(exc) if leak_safe else None)

    @api.exception_handler(NinjaValidationError)
    def _validation(request, exc):
        # pydantic's per-error dicts also carry `input` (the caller's own
        # payload echoed back) and `ctx`/`url` (not JSON-safe / noise) —
        # only location, message, and error type are contract.
        errors = [
            {key: error.get(key) for key in ("loc", "msg", "type") if key in error}
            for error in exc.errors
        ]
        return problem_response("validation_error", extensions={"errors": errors})

    @api.exception_handler(Http404)
    def _not_found(request, exc):
        # No detail: Django's Http404 message names the model class.
        return problem_response("not_found")

    @api.exception_handler(Exception)
    def _unhandled(request, exc):
        logger.exception(
            "unhandled exception on %s %s", request.method, request.path
        )
        return problem_response("internal_error")
