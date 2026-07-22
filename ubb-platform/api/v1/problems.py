"""Central problem+json rendering (#78): the nine dialects die here.

One handler layer on the one NinjaAPI turns every error — raised ``Problem``s,
stray ``HttpError``s, request-validation failures, storage-constraint
``DataError``s (#103), ``Http404``, auth failures, and unhandled exceptions —
into RFC 9457 ``application/problem+json`` with a registry ``code``
(``core/problems.py``). Nothing below the API layer builds
an error body by hand; endpoints raise, this module renders.

5xx bodies never leak internals: the unhandled-exception handler logs the
traceback server-side and serves a bare ``internal_error`` problem.
"""
import json
import logging

from django.db import DataError
from django.http import Http404, HttpResponse
from ninja.errors import (
    AuthenticationError as NinjaAuthenticationError,
    HttpError,
    ValidationError as NinjaValidationError,
)

from core.identifiers import is_path_identifier_error
from core.problems import PROBLEM_TYPE_BASE, PROBLEMS, Problem

logger = logging.getLogger(__name__)

# The one media type of the dialect: what problem_response serves, what the
# middleware below detects, and what document_problem_media_type writes into
# the OpenAPI document (#104).
PROBLEM_MEDIA_TYPE = "application/problem+json"

# Fallback mapping for HttpErrors that predate the conversion (and ninja's own
# internals, e.g. the 400 "Cannot parse request body"). Converted code raises
# Problem directly; this lane keeps any straggler on-dialect. An unmapped
# status collapses to the nearest generic (bad_request / internal_error) —
# the registry pins one status per code, so a foreign status can't be served.
_CODE_BY_STATUS = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    410: "gone",
    422: "validation_error",
    429: "rate_limit_exceeded",
    503: "service_unavailable",
}


# The one wire detail for the DataError→422 lane (#103). The driver's own
# message can name column types ("character varying(5)") or echo input, so
# it goes to the server log, never the body.
DATA_ERROR_DETAIL = (
    "A value in the request cannot be stored: it is out of range, "
    "too long, or contains unsupported characters."
)


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
        content_type=PROBLEM_MEDIA_TYPE,
    )
    for name, value in (headers or {}).items():
        response[name] = value
    return response


_PROBLEM_SCHEMA_REF = "#/components/schemas/ProblemOut"


def document_problem_media_type(schema):
    """The document side of the dialect (#104). ninja exports every
    ``response=`` model under the JSON renderer's ``application/json`` —
    including the ``ProblemOut`` error statuses, which the handlers below
    actually serve as ``application/problem+json``. Re-key exactly those
    content maps so the document tells the truth about the wire. Success
    bodies and the ``webhooks`` section (event deliveries, not error
    responses) are untouched. Mutates and returns ``schema``."""
    for path_item in schema.get("paths", {}).values():
        for operation in path_item.values():
            if not isinstance(operation, dict):
                continue
            for response in operation.get("responses", {}).values():
                content = response.get("content") or {}
                body = content.get("application/json")
                if body and body.get("schema", {}).get("$ref") == _PROBLEM_SCHEMA_REF:
                    content[PROBLEM_MEDIA_TYPE] = content.pop("application/json")
    return schema


def install_problem_handlers(api):
    @api.exception_handler(Problem)
    def _problem(request, exc):
        return problem_response(
            exc.code, exc.detail, extensions=exc.extensions, headers=exc.headers
        )

    @api.exception_handler(HttpError)
    def _http_error(request, exc):
        code = _CODE_BY_STATUS.get(
            exc.status_code,
            "bad_request" if exc.status_code < 500 else "internal_error",
        )
        leak_safe = exc.status_code < 500 and not isinstance(
            exc, NinjaAuthenticationError
        )
        headers = {"Retry-After": "60"} if exc.status_code == 429 else None
        return problem_response(
            code, str(exc) if leak_safe else None, headers=headers)

    @api.exception_handler(NinjaValidationError)
    def _validation(request, exc):
        # #102: a path identifier that does not parse as a UUID cannot name
        # a resource — indistinguishable from a nonexistent one, so it takes
        # the same bare 404 lane as Http404. Only when nothing else failed:
        # any other error keeps the 422 lane, mirroring the ordering a
        # well-formed-but-unknown identifier gets (validation answers first,
        # the lookup never runs).
        if exc.errors and all(is_path_identifier_error(e) for e in exc.errors):
            return problem_response("not_found")
        # pydantic's per-error dicts also carry `input` (the caller's own
        # payload echoed back) and `ctx`/`url` (not JSON-safe / noise) —
        # only location, message, and error type are contract.
        errors = [
            {key: error.get(key) for key in ("loc", "msg", "type") if key in error}
            for error in exc.errors
        ]
        return problem_response("validation_error", extensions={"errors": errors})

    @api.exception_handler(DataError)
    def _data_error(request, exc):
        # #103: the committed document types some fields loosely (unbounded
        # integer, open string), so doc-legal values can still violate a
        # storage constraint — NUL bytes in text, int4 overflow, varchar
        # overflow — and surface as the driver's DataError. The value is
        # the caller's problem, not a server fault: answer the validation
        # lane. Only DataError takes this mapping (ninja resolves handlers
        # by exception MRO) — every other DatabaseError stays a 500.
        logger.warning(
            "request value rejected by storage on %s %s: %s",
            request.method, request.path, exc,
        )
        return problem_response("validation_error", DATA_ERROR_DETAIL)

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


class MethodNotAllowedProblemMiddleware:
    """The one error the handlers cannot reach: a wrong-method request is
    answered by ninja/Django with a plain ``HttpResponseNotAllowed`` before
    any exception handler runs. Rewrite it onto the dialect (keeping the
    ``Allow`` header) so the surface's zero-non-problem+json promise holds.
    Registered in ``config/settings.py``; scoped to the versioned mount."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if (
            response.status_code == 405
            and request.path.startswith("/api/v1/")
            and response.get("Content-Type") != PROBLEM_MEDIA_TYPE
        ):
            allow = response.get("Allow", "")
            return problem_response(
                "method_not_allowed",
                headers={"Allow": allow} if allow else None,
            )
        return response
