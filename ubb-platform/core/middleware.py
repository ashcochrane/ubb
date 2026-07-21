"""
Correlation ID middleware for request tracing.

Reads X-Correlation-ID from incoming requests, validates as UUID format,
generates fresh UUID if missing/invalid, and sets it on the response.
"""

import uuid
import re

from apps.platform.audit.actors import clear_current_actor
from core.logging import correlation_id_var

UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


class CorrelationIdMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        incoming_id = request.META.get("HTTP_X_CORRELATION_ID", "")
        if incoming_id and UUID_PATTERN.match(incoming_id) and len(incoming_id) <= 36:
            cid = incoming_id
        else:
            cid = str(uuid.uuid4())

        token = correlation_id_var.set(cid)
        try:
            response = self.get_response(request)
            response["X-Correlation-ID"] = cid
            return response
        finally:
            correlation_id_var.reset(token)


class RequestActorMiddleware:
    """Clear the request-scoped audit actor at request end.

    The audit actor is captured mid-request at the auth seam (``core/auth.py`` for
    tenant principals, ``core/widget_auth.py`` for end customers), not at request
    start — so unlike the correlation id there is no token to reset. WSGI worker
    threads are pooled and a ``ContextVar`` set on a thread outlives the request
    that set it, so without this reset one request's principal could leak into the
    next *unauthenticated* request on the same thread. Resetting to ``None`` in a
    finally guarantees every request starts with a clean, unattributed actor.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        try:
            return self.get_response(request)
        finally:
            clear_current_actor()
