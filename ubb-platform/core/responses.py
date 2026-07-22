"""JSON response helpers for Router-based handlers.

The single-API restructure (#77) turned the twelve per-mount ``NinjaAPI``
instances into ``Router``s, which have no ``create_response``. This mirrors
``NinjaAPI.create_response`` byte-for-byte for the default JSON renderer —
same encoder, same ``application/json; charset=utf-8`` content type — so
handler call sites only swap the callable name.
"""
from django.http import HttpRequest, HttpResponse
from ninja import Schema
from ninja.renderers import JSONRenderer


class StatusResponse(Schema):
    """The tiny cross-product acknowledgement body: ``{"status": "<word>"}``.

    One shared out-type (#98) for the endpoints that answer a mutation with a
    single status word (``ok`` / ``deleted`` / ``no_override`` / ``deactivated``
    / ``revoked`` / …) — kernel-owned so every product can declare it without
    crossing a product boundary (ADR-001). The value stays an open string
    (ADR-003 open enums).
    """
    status: str

_renderer = JSONRenderer()
_content_type = f"{_renderer.media_type}; charset={_renderer.charset}"


def json_response(request: HttpRequest, data, *, status: int) -> HttpResponse:
    content = _renderer.render(request, data, response_status=status)
    return HttpResponse(content, status=status, content_type=_content_type)
